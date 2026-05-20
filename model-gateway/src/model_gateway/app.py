from __future__ import annotations

import csv
import io
import sqlite3
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from model_gateway.config import Settings
from model_gateway.database import (
    DISPATCH_MODE_AUTO,
    DISPATCH_MODE_CONSOLE_API,
    DISPATCH_MODE_SSH,
    EVENT_ACTIVE,
    EVENT_CLOSED,
    GatewayStateError,
    NewSubmission,
    ROLE_ADMIN,
    ROLE_USER,
    ROUND_CLOSED,
    ROUND_OPEN,
    SETTING_DEFAULT_TEAM_MAX_MEMBERS,
    SETTING_REGISTRATION_ENABLED,
    TEAM_ACTIVE,
    TEAM_DISABLED,
    TEAM_LEADER,
    USER_ACTIVE,
    USER_PENDING,
    approve_submission,
    approve_user,
    cancel_dispatch,
    create_event,
    create_dispatch_if_available,
    create_round,
    create_session,
    create_submission,
    create_team,
    create_user,
    create_vehicle,
    default_team_max_members,
    disable_user,
    ensure_bootstrap_admin,
    get_dispatch,
    get_active_round,
    get_setting,
    get_team_by_name,
    get_user,
    get_user_by_session,
    get_vehicle,
    init_db,
    is_registration_enabled,
    join_team,
    join_team_by_code,
    leave_team,
    list_audit_logs,
    list_dispatch_attempts,
    list_dispatches,
    list_events,
    list_latest_vehicle_health,
    list_rounds,
    list_sessions,
    list_submissions,
    list_teams,
    list_users,
    list_vehicles,
    login_locked,
    move_user_to_team,
    next_submission_version,
    record_audit_log,
    record_login_attempt,
    record_vehicle_health_check,
    regenerate_team_join_code,
    reject_submission,
    remove_team_member,
    reset_user_password,
    revoke_session,
    revoke_session_by_id,
    set_setting,
    set_submission_candidate,
    team_members_snapshot,
    update_event,
    update_round,
    update_team,
    update_team_member_role,
    update_user,
    update_vehicle,
    validate_round_dispatch,
    validate_round_upload,
)
from model_gateway.security import CredentialCodec, PasswordPolicyError, generate_password, new_csrf_token, validate_password_strength
from model_gateway.ssh_delivery import SshDeliveryClient, SshDeliveryError
from model_gateway.storage import UploadValidationError, save_upload
from model_gateway.vehicle import VehicleClient, VehicleClientError
from model_gateway.worker import DispatchWorker


PACKAGE_DIR = Path(__file__).parent
USER_COOKIE_NAME = "model_gateway_user_session"
ADMIN_COOKIE_NAME = "model_gateway_admin_session"
CSRF_COOKIE_NAME = "model_gateway_csrf"


def create_app(settings: Settings | None = None) -> FastAPI:
    explicit_settings = settings is not None
    settings = settings or Settings()
    settings.validate_runtime()
    worker: DispatchWorker | None = None

    def initialize_storage() -> None:
        settings.ensure_directories()
        init_db(settings.db_path)
        ensure_bootstrap_admin(
            settings.db_path,
            settings.bootstrap_admin_username,
            settings.bootstrap_admin_password,
        )

    if explicit_settings:
        initialize_storage()
        app = FastAPI(title="DeepRacer Model Gateway")
    else:
        @asynccontextmanager
        async def lifespan(app_: FastAPI):  # type: ignore[no-untyped-def]
            nonlocal worker
            initialize_storage()
            if settings.dispatch_worker_enabled:
                worker = DispatchWorker(settings)
                worker.start()
            try:
                yield
            finally:
                if worker is not None:
                    worker.stop()

        app = FastAPI(title="DeepRacer Model Gateway", lifespan=lifespan)

    app.state.settings = settings
    templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))
    app.mount("/static", StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static")

    @app.middleware("http")
    async def csrf_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        token = request.cookies.get(CSRF_COOKIE_NAME) or new_csrf_token()
        request.state.csrf_token = token
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            submitted = request.headers.get("x-csrf-token", "") or request.query_params.get("csrf_token", "")
            if submitted != token:
                return Response("Invalid CSRF token", status_code=403)
        response = await call_next(request)
        if request.cookies.get(CSRF_COOKIE_NAME) != token:
            response.set_cookie(CSRF_COOKIE_NAME, token, httponly=True, samesite="lax", secure=settings.cookie_secure)
        return response

    def user_from_request(request: Request) -> dict | None:
        return get_user_by_session(
            settings.db_path,
            request.cookies.get(USER_COOKIE_NAME),
            role=ROLE_USER,
            max_age_seconds=settings.session_max_age_seconds,
        )

    def admin_from_request(request: Request) -> dict | None:
        return get_user_by_session(
            settings.db_path,
            request.cookies.get(ADMIN_COOKIE_NAME),
            role=ROLE_ADMIN,
            max_age_seconds=settings.session_max_age_seconds,
        )

    def redirect(url: str, **params: str) -> RedirectResponse:
        if params:
            url += "?" + urlencode(params)
        return RedirectResponse(url, status_code=303)

    def set_session_cookie(response: Response, name: str, token: str) -> None:
        response.set_cookie(name, token, httponly=True, samesite="lax", secure=settings.cookie_secure, max_age=settings.session_max_age_seconds)

    def remote_addr(request: Request) -> str:
        return request.client.host if request.client else ""

    def audit(request: Request, actor: dict | None, action: str, target_type: str = "", target_id: str | int = "", message: str = "") -> None:
        record_audit_log(
            settings.db_path,
            actor_user_id=int(actor["id"]) if actor else None,
            actor_username=str(actor.get("username", "")) if actor else "",
            actor_role=str(actor.get("role", "")) if actor else "",
            action=action,
            target_type=target_type,
            target_id=target_id,
            message=message,
            remote_addr=remote_addr(request),
        )

    def base_context(request: Request, **context: object) -> dict[str, object]:
        return {
            "request": request,
            "csrf_token": request.state.csrf_token,
            "current_user": user_from_request(request),
            "current_admin": admin_from_request(request),
            "registration_enabled": is_registration_enabled(settings.db_path),
            "credential_warning": not bool(settings.credential_secret),
            **context,
        }

    def require_user(request: Request) -> dict:
        user = user_from_request(request)
        if user is None:
            raise HTTPException(status_code=303, headers={"Location": "/login"})
        return user

    def require_admin(request: Request) -> dict:
        admin = admin_from_request(request)
        if admin is None:
            raise HTTPException(status_code=303, headers={"Location": "/admin/login"})
        return admin

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> RedirectResponse:
        if admin_from_request(request):
            return redirect("/admin")
        if user_from_request(request):
            return redirect("/dashboard")
        return redirect("/login")

    @app.get("/login", response_class=HTMLResponse)
    def user_login_form(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "login.html", base_context(request, mode="user", action="/login"))

    @app.post("/login")
    def user_login(request: Request, username: str = Form(...), password: str = Form(...)) -> Response:
        from model_gateway.database import authenticate_user

        if login_locked(settings.db_path, username, role=ROLE_USER, limit=settings.login_rate_limit, lockout_seconds=settings.login_lockout_seconds):
            return redirect("/login", error="Too many failed login attempts. Try again later.")
        user = authenticate_user(settings.db_path, username, password, role=ROLE_USER)
        if user is None:
            record_login_attempt(settings.db_path, username, role=ROLE_USER, remote_addr=remote_addr(request), succeeded=False)
            return redirect("/login", error="Invalid username, password, or account status")
        record_login_attempt(settings.db_path, username, role=ROLE_USER, remote_addr=remote_addr(request), succeeded=True)
        token = create_session(
            settings.db_path,
            int(user["id"]),
            request.headers.get("user-agent", ""),
            max_age_seconds=settings.session_max_age_seconds,
        )
        response = redirect("/dashboard")
        set_session_cookie(response, USER_COOKIE_NAME, token)
        return response

    @app.post("/logout")
    def user_logout(request: Request) -> Response:
        token = request.cookies.get(USER_COOKIE_NAME)
        if token:
            revoke_session(settings.db_path, token)
        response = redirect("/login")
        response.delete_cookie(USER_COOKIE_NAME)
        return response

    @app.get("/register", response_class=HTMLResponse)
    def register_form(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "register.html", base_context(request))

    @app.post("/register")
    def register(username: str = Form(...), display_name: str = Form(...), password: str = Form(...)) -> Response:
        if not is_registration_enabled(settings.db_path):
            return redirect("/register", error="Self registration is closed")
        try:
            validate_password_strength(password)
            create_user(settings.db_path, username, display_name, password, role=ROLE_USER, status=USER_PENDING)
            return redirect("/login", notice="Registration submitted. Wait for admin approval.")
        except (GatewayStateError, PasswordPolicyError, sqlite3.IntegrityError) as exc:
            return redirect("/register", error=str(exc))

    @app.get("/dashboard", response_class=HTMLResponse)
    def dashboard(request: Request) -> HTMLResponse:
        user = require_user(request)
        team = get_user_team_for_app(settings.db_path, int(user["id"]))
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            base_context(
                request,
                user=user,
                team=team,
                submissions=list_submissions(settings.db_path, user_id=int(user["id"])),
                notice=request.query_params.get("notice"),
                error=request.query_params.get("error"),
            ),
        )

    @app.get("/teams", response_class=HTMLResponse)
    def teams_page(request: Request) -> HTMLResponse:
        user = require_user(request)
        team = get_user_team_for_app(settings.db_path, int(user["id"]))
        return templates.TemplateResponse(
            request,
            "teams.html",
            base_context(request, user=user, team=team, notice=request.query_params.get("notice"), error=request.query_params.get("error")),
        )

    @app.post("/teams")
    def create_user_team(request: Request, name: str = Form(...)) -> Response:
        user = require_user(request)
        try:
            max_members = default_team_max_members(settings.db_path)
            create_team(settings.db_path, name, created_by_user_id=int(user["id"]), max_members=max_members, leader_user_id=int(user["id"]))
            return redirect("/teams", notice="Team created")
        except (GatewayStateError, sqlite3.IntegrityError) as exc:
            return redirect("/teams", error=str(exc))

    @app.post("/teams/join")
    def join_user_team(request: Request, join_code: str = Form(...)) -> Response:
        user = require_user(request)
        try:
            join_team_by_code(settings.db_path, join_code, int(user["id"]))
            return redirect("/teams", notice="Joined team")
        except GatewayStateError as exc:
            return redirect("/teams", error=str(exc))

    @app.post("/teams/leave")
    def leave_user_team(request: Request) -> Response:
        user = require_user(request)
        leave_team(settings.db_path, int(user["id"]))
        return redirect("/teams", notice="Left team")

    @app.get("/upload", response_class=HTMLResponse)
    def upload_form(request: Request) -> HTMLResponse:
        user = require_user(request)
        team = get_user_team_for_app(settings.db_path, int(user["id"]))
        return templates.TemplateResponse(request, "upload.html", base_context(request, user=user, team=team, active_round=get_active_round(settings.db_path)))

    @app.post("/upload", response_class=HTMLResponse)
    async def upload_model(
        request: Request,
        model_name: str = Form(...),
        notes: str = Form(""),
        file: UploadFile = File(...),
    ) -> HTMLResponse:
        user = require_user(request)
        team = get_user_team_for_app(settings.db_path, int(user["id"]))
        if team is None:
            return templates.TemplateResponse(
                request,
                "upload.html",
                base_context(request, user=user, team=None, error="Join or create a team before uploading."),
                status_code=400,
            )
        try:
            active_round = get_active_round(settings.db_path)
            validate_round_upload(settings.db_path, int(team["id"]), active_round)
            stored = await save_upload(file, settings.upload_dir, settings.max_upload_bytes)
            round_id = int(active_round["id"]) if active_round else None
            version_number = next_submission_version(settings.db_path, int(team["id"]), round_id)
            submission = NewSubmission(
                user_id=int(user["id"]),
                team_id=int(team["id"]),
                round_id=round_id,
                version_number=version_number,
                is_candidate=True,
                username_snapshot=str(user["username"]),
                display_name_snapshot=str(user["display_name"]),
                team_name_snapshot=str(team["name"]),
                team_members_snapshot=team_members_snapshot(team),
                model_name=model_name.strip(),
                notes=notes.strip(),
                original_filename=stored.original_filename,
                storage_path=str(stored.storage_path),
                sha256=stored.sha256,
                size_bytes=stored.size_bytes,
                warning=stored.warning,
            )
            submission_id = create_submission(settings.db_path, submission)
        except (UploadValidationError, GatewayStateError) as exc:
            return templates.TemplateResponse(
                request,
                "upload.html",
                base_context(request, user=user, team=team, active_round=get_active_round(settings.db_path), error=str(exc), model_name=model_name, notes=notes),
                status_code=400,
            )
        return templates.TemplateResponse(
            request,
            "upload_success.html",
            base_context(request, submission_id=submission_id, model_name=model_name, warning=stored.warning),
        )

    @app.get("/admin/login", response_class=HTMLResponse)
    def admin_login_form(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "login.html", base_context(request, mode="admin", action="/admin/login"))

    @app.post("/admin/login")
    def admin_login(request: Request, username: str = Form(...), password: str = Form(...)) -> Response:
        from model_gateway.database import authenticate_user

        if login_locked(settings.db_path, username, role=ROLE_ADMIN, limit=settings.login_rate_limit, lockout_seconds=settings.login_lockout_seconds):
            return redirect("/admin/login", error="Too many failed login attempts. Try again later.")
        admin = authenticate_user(settings.db_path, username, password, role=ROLE_ADMIN)
        if admin is None:
            record_login_attempt(settings.db_path, username, role=ROLE_ADMIN, remote_addr=remote_addr(request), succeeded=False)
            return redirect("/admin/login", error="Invalid admin username, password, or account status")
        record_login_attempt(settings.db_path, username, role=ROLE_ADMIN, remote_addr=remote_addr(request), succeeded=True)
        audit(request, admin, "admin.login", "user", int(admin["id"]))
        token = create_session(
            settings.db_path,
            int(admin["id"]),
            request.headers.get("user-agent", ""),
            max_age_seconds=settings.session_max_age_seconds,
        )
        response = redirect("/admin")
        set_session_cookie(response, ADMIN_COOKIE_NAME, token)
        return response

    @app.post("/admin/logout")
    def admin_logout(request: Request) -> Response:
        token = request.cookies.get(ADMIN_COOKIE_NAME)
        if token:
            revoke_session(settings.db_path, token)
        response = redirect("/admin/login")
        response.delete_cookie(ADMIN_COOKIE_NAME)
        return response

    @app.get("/admin", response_class=HTMLResponse)
    def admin_dashboard(request: Request) -> HTMLResponse:
        require_admin(request)
        q = request.query_params.get("q", "")
        status = request.query_params.get("status", "")
        round_id = _optional_int(request.query_params.get("round_id"))
        team_id = _optional_int(request.query_params.get("team_id"))
        return templates.TemplateResponse(
            request,
            "admin.html",
            base_context(
                request,
                submissions=list_submissions(settings.db_path, q=q, status=status or None, round_id=round_id, team_id=team_id),
                vehicles=list_vehicles(settings.db_path),
                dispatches=list_dispatches(settings.db_path),
                teams=list_teams(settings.db_path),
                rounds=list_rounds(settings.db_path),
                filters={"q": q, "status": status, "round_id": round_id, "team_id": team_id},
                notice=request.query_params.get("notice"),
                error=request.query_params.get("error"),
            ),
        )

    @app.get("/admin/users", response_class=HTMLResponse)
    def admin_users(request: Request) -> HTMLResponse:
        require_admin(request)
        q = request.query_params.get("q", "").strip().lower()
        role_filter = request.query_params.get("role", "")
        status_filter = request.query_params.get("status", "")
        users = list_users(settings.db_path)
        if q:
            users = [u for u in users if q in str(u["username"]).lower() or q in str(u["display_name"]).lower() or q in str(u.get("team_name") or "").lower()]
        if role_filter:
            users = [u for u in users if u["role"] == role_filter]
        if status_filter:
            users = [u for u in users if u["status"] == status_filter]
        return templates.TemplateResponse(
            request,
            "admin_users.html",
            base_context(
                request,
                users=users,
                sessions=list_sessions(settings.db_path),
                teams=list_teams(settings.db_path),
                filters={"q": q, "role": role_filter, "status": status_filter},
                generated=request.query_params.get("generated"),
                notice=request.query_params.get("notice"),
                error=request.query_params.get("error"),
            ),
        )

    @app.post("/admin/users")
    def admin_create_user(
        request: Request,
        username: str = Form(...),
        display_name: str = Form(""),
        role: str = Form(ROLE_USER),
        password: str = Form(""),
        status: str = Form(USER_ACTIVE),
    ) -> Response:
        admin = require_admin(request)
        password = password or generate_password()
        try:
            validate_password_strength(password)
            create_user(settings.db_path, username, display_name or username, password, role=role, status=status)
            audit(request, admin, "user.create", "user", username, f"role={role} status={status}")
            return redirect("/admin/users", generated=f"{username},{password}")
        except (GatewayStateError, PasswordPolicyError, sqlite3.IntegrityError) as exc:
            return redirect("/admin/users", error=str(exc))

    @app.post("/admin/users/batch")
    def admin_batch_users(request: Request, prefix: str = Form("racer"), count: int = Form(...), team_name: str = Form("")) -> Response:
        admin = require_admin(request)
        rows = [("username", "display_name", "team_name", "password")]
        team_id = _team_for_import(settings.db_path, team_name) if team_name.strip() else None
        for index in range(1, max(0, count) + 1):
            username = f"{prefix}{index:03d}".lower()
            password = generate_password()
            try:
                user_id = create_user(settings.db_path, username, username, password, role=ROLE_USER, status=USER_ACTIVE)
                if team_id is not None:
                    join_team(settings.db_path, team_id, user_id)
                rows.append((username, username, team_name.strip(), password))
            except sqlite3.IntegrityError:
                continue
        audit(request, admin, "user.batch_create", "user", "", f"prefix={prefix} count={count} team={team_name}")
        return _csv_response(rows, "generated-users.csv")

    @app.post("/admin/users/import")
    async def admin_import_users(request: Request, file: UploadFile = File(...)) -> Response:
        admin = require_admin(request)
        content = (await file.read()).decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        rows = [("username", "display_name", "team_name", "password")]
        for row in reader:
            username = (row.get("username") or "").strip()
            if not username:
                continue
            display_name = (row.get("display_name") or username).strip()
            team_name = (row.get("team_name") or "").strip()
            password = (row.get("password") or generate_password()).strip()
            try:
                validate_password_strength(password)
                user_id = create_user(settings.db_path, username, display_name, password, role=ROLE_USER, status=USER_ACTIVE)
                if team_name:
                    join_team(settings.db_path, _team_for_import(settings.db_path, team_name), user_id)
                rows.append((username, display_name, team_name, password))
            except (GatewayStateError, PasswordPolicyError, sqlite3.IntegrityError):
                continue
        audit(request, admin, "user.import_csv", "user", "", f"rows={max(0, len(rows)-1)}")
        return _csv_response(rows, "imported-users.csv")

    @app.post("/admin/users/{user_id}/approve")
    def admin_approve_user(request: Request, user_id: int) -> Response:
        admin = require_admin(request)
        try:
            approve_user(settings.db_path, user_id)
            audit(request, admin, "user.approve", "user", user_id)
            return redirect("/admin/users", notice="User approved")
        except GatewayStateError as exc:
            return redirect("/admin/users", error=str(exc))

    @app.post("/admin/users/{user_id}/update")
    def admin_update_user(
        request: Request,
        user_id: int,
        username: str = Form(...),
        display_name: str = Form(""),
        role: str = Form(ROLE_USER),
        status: str = Form(USER_ACTIVE),
        team_id: str = Form(""),
        team_role: str = Form("member"),
    ) -> Response:
        admin = require_admin(request)
        try:
            update_user(
                settings.db_path,
                user_id,
                username=username,
                display_name=display_name,
                role=role,
                status=status,
                team_id=_optional_int(team_id),
                team_role=team_role,
            )
            audit(request, admin, "user.update", "user", user_id, f"username={username} role={role} status={status}")
            return redirect("/admin/users", notice="User updated")
        except (GatewayStateError, sqlite3.IntegrityError) as exc:
            return redirect("/admin/users", error=str(exc))

    @app.post("/admin/users/{user_id}/disable")
    def admin_disable_user(request: Request, user_id: int) -> Response:
        admin = require_admin(request)
        try:
            disable_user(settings.db_path, user_id)
            audit(request, admin, "user.disable", "user", user_id)
            return redirect("/admin/users", notice="User disabled")
        except GatewayStateError as exc:
            return redirect("/admin/users", error=str(exc))

    @app.post("/admin/users/{user_id}/reset-password")
    def admin_reset_password(request: Request, user_id: int) -> Response:
        admin = require_admin(request)
        password = reset_user_password(settings.db_path, user_id)
        user = get_user(settings.db_path, user_id)
        audit(request, admin, "user.reset_password", "user", user_id)
        return redirect("/admin/users", generated=f"{user['username'] if user else user_id},{password}")

    @app.post("/admin/sessions/{session_id}/revoke")
    def admin_revoke_session(request: Request, session_id: int) -> Response:
        require_admin(request)
        revoke_session_by_id(settings.db_path, session_id)
        return redirect("/admin/users", notice="Session revoked")

    @app.get("/admin/teams", response_class=HTMLResponse)
    def admin_teams(request: Request) -> HTMLResponse:
        require_admin(request)
        q = request.query_params.get("q", "").strip().lower()
        status_filter = request.query_params.get("status", "")
        teams = list_teams(settings.db_path)
        if q:
            teams = [t for t in teams if q in str(t["name"]).lower() or q in str(t["join_code"]).lower()]
        if status_filter:
            teams = [t for t in teams if t["status"] == status_filter]
        return templates.TemplateResponse(
            request,
            "admin_teams.html",
            base_context(
                request,
                teams=teams,
                users=list_users(settings.db_path),
                filters={"q": q, "status": status_filter},
                default_team_max_members=get_setting(settings.db_path, SETTING_DEFAULT_TEAM_MAX_MEMBERS, ""),
                registration_enabled=is_registration_enabled(settings.db_path),
                notice=request.query_params.get("notice"),
                error=request.query_params.get("error"),
            ),
        )

    @app.post("/admin/teams")
    def admin_create_team(request: Request, name: str = Form(...), max_members: str = Form("")) -> Response:
        admin = require_admin(request)
        try:
            team_id = create_team(settings.db_path, name, created_by_user_id=int(admin["id"]), max_members=_optional_int(max_members))
            audit(request, admin, "team.create", "team", team_id, name)
            return redirect("/admin/teams", notice="Team created")
        except (GatewayStateError, sqlite3.IntegrityError) as exc:
            return redirect("/admin/teams", error=str(exc))

    @app.post("/admin/teams/{team_id}/update")
    def admin_update_team(
        request: Request,
        team_id: int,
        name: str = Form(""),
        max_members: str = Form(""),
        status: str = Form(TEAM_ACTIVE),
    ) -> Response:
        admin = require_admin(request)
        try:
            update_team(settings.db_path, team_id, name=name, max_members=_optional_int(max_members), status=status)
            audit(request, admin, "team.update", "team", team_id, f"name={name} status={status}")
            return redirect("/admin/teams", notice="Team updated")
        except (GatewayStateError, sqlite3.IntegrityError) as exc:
            return redirect("/admin/teams", error=str(exc))

    @app.post("/admin/teams/{team_id}/members")
    def admin_add_team_member(
        request: Request,
        team_id: int,
        user_id: int = Form(...),
        role: str = Form(TEAM_LEADER),
    ) -> Response:
        admin = require_admin(request)
        try:
            move_user_to_team(settings.db_path, user_id, team_id, role=role)
            audit(request, admin, "team.member_move", "team", team_id, f"user={user_id} role={role}")
            return redirect("/admin/teams", notice="Team member updated")
        except GatewayStateError as exc:
            return redirect("/admin/teams", error=str(exc))

    @app.post("/admin/teams/{team_id}/regenerate-code")
    def admin_regenerate_team_code(request: Request, team_id: int) -> Response:
        admin = require_admin(request)
        try:
            regenerate_team_join_code(settings.db_path, team_id)
            audit(request, admin, "team.regenerate_code", "team", team_id)
            return redirect("/admin/teams", notice="Team join code regenerated")
        except GatewayStateError as exc:
            return redirect("/admin/teams", error=str(exc))

    @app.post("/admin/teams/{team_id}/members/{user_id}/remove")
    def admin_remove_team_member(request: Request, team_id: int, user_id: int) -> Response:
        admin = require_admin(request)
        remove_team_member(settings.db_path, team_id, user_id)
        audit(request, admin, "team.member_remove", "team", team_id, f"user={user_id}")
        return redirect("/admin/teams", notice="Team member removed")

    @app.post("/admin/teams/{team_id}/members/{user_id}/role")
    def admin_update_team_member_role(
        request: Request,
        team_id: int,
        user_id: int,
        role: str = Form(...),
    ) -> Response:
        admin = require_admin(request)
        try:
            update_team_member_role(settings.db_path, team_id, user_id, role)
            audit(request, admin, "team.member_role", "team", team_id, f"user={user_id} role={role}")
            return redirect("/admin/teams", notice="Team member role updated")
        except GatewayStateError as exc:
            return redirect("/admin/teams", error=str(exc))

    @app.post("/admin/settings/registration")
    def admin_registration_settings(
        request: Request,
        registration_enabled: str = Form("false"),
        default_team_max_members: str = Form(""),
    ) -> Response:
        admin = require_admin(request)
        set_setting(settings.db_path, SETTING_REGISTRATION_ENABLED, "true" if registration_enabled == "true" else "false")
        set_setting(settings.db_path, SETTING_DEFAULT_TEAM_MAX_MEMBERS, default_team_max_members.strip())
        audit(request, admin, "settings.registration", "settings", SETTING_REGISTRATION_ENABLED, f"enabled={registration_enabled}")
        return redirect("/admin/teams", notice="Settings saved")

    @app.get("/admin/vehicles", response_class=HTMLResponse)
    def admin_vehicles(request: Request) -> HTMLResponse:
        require_admin(request)
        q = request.query_params.get("q", "").strip().lower()
        mode_filter = request.query_params.get("mode", "")
        vehicles = list_vehicles(settings.db_path)
        health = list_latest_vehicle_health(settings.db_path)
        for vehicle in vehicles:
            vehicle["health"] = health.get(int(vehicle["id"]))
        if q:
            vehicles = [v for v in vehicles if q in str(v["name"]).lower() or q in str(v.get("ssh_host") or "").lower() or q in str(v.get("console_url") or "").lower()]
        if mode_filter:
            vehicles = [v for v in vehicles if v["delivery_mode"] == mode_filter]
        return templates.TemplateResponse(
            request,
            "admin_vehicles.html",
            base_context(
                request,
                vehicles=vehicles,
                filters={"q": q, "mode": mode_filter},
                notice=request.query_params.get("notice"),
                error=request.query_params.get("error"),
            ),
        )

    @app.post("/admin/vehicles")
    def add_vehicle(
        request: Request,
        name: str = Form(...),
        console_url: str = Form(""),
        console_password: str = Form(""),
        delivery_mode: str = Form(DISPATCH_MODE_AUTO),
        ssh_host: str = Form(""),
        ssh_port: int = Form(22),
        ssh_username: str = Form(""),
        ssh_password: str = Form(""),
        ssh_private_key_path: str = Form(""),
        ssh_host_key_sha256: str = Form(""),
        ssh_remote_artifact_root: str = Form("/opt/aws/deepracer/artifacts"),
        ssh_install_command_template: str = Form(""),
        notes: str = Form(""),
    ) -> Response:
        admin = require_admin(request)
        if console_url and not console_url.startswith(("http://", "https://")):
            return redirect("/admin/vehicles", error="Vehicle URL must start with http:// or https://")
        try:
            create_vehicle(
                settings.db_path,
                name,
                console_url,
                console_password or None,
                credential_secret=settings.credential_secret,
                delivery_mode=delivery_mode,
                ssh_host=ssh_host,
                ssh_port=ssh_port,
                ssh_username=ssh_username,
                ssh_password=ssh_password or None,
                ssh_private_key_path=ssh_private_key_path,
                ssh_host_key_sha256=ssh_host_key_sha256,
                ssh_remote_artifact_root=ssh_remote_artifact_root,
                ssh_install_command_template=ssh_install_command_template,
                notes=notes,
            )
            audit(request, admin, "vehicle.create", "vehicle", name)
            return redirect("/admin/vehicles", notice="Vehicle saved")
        except GatewayStateError as exc:
            return redirect("/admin/vehicles", error=str(exc))

    @app.post("/admin/vehicles/{vehicle_id}/update")
    def update_vehicle_route(
        request: Request,
        vehicle_id: int,
        name: str = Form(...),
        console_url: str = Form(""),
        console_password: str = Form(""),
        clear_console_password: str = Form("false"),
        delivery_mode: str = Form(DISPATCH_MODE_AUTO),
        ssh_host: str = Form(""),
        ssh_port: int = Form(22),
        ssh_username: str = Form(""),
        ssh_password: str = Form(""),
        clear_ssh_password: str = Form("false"),
        ssh_private_key_path: str = Form(""),
        ssh_host_key_sha256: str = Form(""),
        ssh_remote_artifact_root: str = Form("/opt/aws/deepracer/artifacts"),
        ssh_install_command_template: str = Form(""),
        notes: str = Form(""),
    ) -> Response:
        admin = require_admin(request)
        try:
            update_vehicle(
                settings.db_path,
                vehicle_id,
                name=name,
                console_url=console_url,
                console_password=console_password or None,
                clear_console_password=clear_console_password == "true",
                credential_secret=settings.credential_secret,
                delivery_mode=delivery_mode,
                ssh_host=ssh_host,
                ssh_port=ssh_port,
                ssh_username=ssh_username,
                ssh_password=ssh_password or None,
                clear_ssh_password=clear_ssh_password == "true",
                ssh_private_key_path=ssh_private_key_path,
                ssh_host_key_sha256=ssh_host_key_sha256,
                ssh_remote_artifact_root=ssh_remote_artifact_root,
                ssh_install_command_template=ssh_install_command_template,
                notes=notes,
            )
            audit(request, admin, "vehicle.update", "vehicle", vehicle_id, f"name={name} mode={delivery_mode}")
            return redirect("/admin/vehicles", notice="Vehicle updated")
        except (GatewayStateError, sqlite3.IntegrityError) as exc:
            return redirect("/admin/vehicles", error=str(exc))

    @app.post("/admin/vehicles/{vehicle_id}/test-console")
    def test_console(request: Request, vehicle_id: int) -> Response:
        require_admin(request)
        from model_gateway.database import get_vehicle

        vehicle = get_vehicle(settings.db_path, vehicle_id)
        if vehicle is None:
            return redirect("/admin/vehicles", error="Vehicle not found")
        codec = CredentialCodec(settings.credential_secret)
        try:
            with VehicleClient(
                vehicle["console_url"],
                codec.decrypt(vehicle.get("console_password_encrypted")),
                timeout_seconds=settings.vehicle_timeout_seconds,
            ) as client:
                client.login()
                client.model_loading_status()
            return redirect("/admin/vehicles", notice="Console API reachable")
        except (VehicleClientError, OSError) as exc:
            return redirect("/admin/vehicles", error=str(exc))

    @app.post("/admin/vehicles/{vehicle_id}/test-ssh")
    def test_ssh(request: Request, vehicle_id: int) -> Response:
        require_admin(request)
        from model_gateway.database import get_vehicle

        vehicle = get_vehicle(settings.db_path, vehicle_id)
        if vehicle is None:
            return redirect("/admin/vehicles", error="Vehicle not found")
        codec = CredentialCodec(settings.credential_secret)
        try:
            client = SshDeliveryClient(
                host=vehicle["ssh_host"],
                port=int(vehicle["ssh_port"]),
                username=vehicle["ssh_username"],
                password=codec.decrypt(vehicle.get("ssh_password_encrypted")),
                private_key_path=vehicle["ssh_private_key_path"],
                host_key_sha256=vehicle.get("ssh_host_key_sha256") or "",
                timeout_seconds=settings.ssh_timeout_seconds,
            )
            client._exec("true")
            return redirect("/admin/vehicles", notice="SSH reachable")
        except SshDeliveryError as exc:
            return redirect("/admin/vehicles", error=str(exc))

    @app.post("/admin/submissions/{submission_id}/approve")
    def approve(request: Request, submission_id: int) -> Response:
        admin = require_admin(request)
        try:
            approve_submission(settings.db_path, submission_id)
            audit(request, admin, "submission.approve", "submission", submission_id)
            return redirect("/admin", notice="Submission approved")
        except GatewayStateError as exc:
            return redirect("/admin", error=str(exc))

    @app.post("/admin/submissions/{submission_id}/reject")
    def reject(request: Request, submission_id: int, reason: str = Form("")) -> Response:
        admin = require_admin(request)
        try:
            reject_submission(settings.db_path, submission_id, reason.strip() or "Rejected by admin")
            audit(request, admin, "submission.reject", "submission", submission_id, reason)
            return redirect("/admin", notice="Submission rejected")
        except GatewayStateError as exc:
            return redirect("/admin", error=str(exc))

    @app.post("/admin/submissions/{submission_id}/dispatch")
    def dispatch(
        request: Request,
        submission_id: int,
        vehicle_id: int = Form(...),
        requested_mode: str = Form(DISPATCH_MODE_AUTO),
    ) -> Response:
        admin = require_admin(request)
        try:
            validate_round_dispatch(settings.db_path, submission_id)
            dispatch_id = create_dispatch_if_available(settings.db_path, submission_id, vehicle_id, requested_mode=requested_mode)
        except GatewayStateError as exc:
            return redirect("/admin", error=str(exc))
        audit(request, admin, "dispatch.queue", "dispatch", dispatch_id, f"submission={submission_id} vehicle={vehicle_id} mode={requested_mode}")
        return redirect("/admin", notice=f"Dispatch {dispatch_id} queued")

    @app.post("/admin/dispatches/{dispatch_id}/cancel")
    def cancel_dispatch_route(request: Request, dispatch_id: int) -> Response:
        admin = require_admin(request)
        try:
            cancel_dispatch(settings.db_path, dispatch_id)
            audit(request, admin, "dispatch.cancel", "dispatch", dispatch_id)
            return redirect("/admin", notice="Dispatch cancellation recorded")
        except GatewayStateError as exc:
            return redirect("/admin", error=str(exc))

    @app.post("/admin/submissions/batch")
    def batch_submissions(request: Request, action: str = Form(...), submission_ids: list = Form([]), reason: str = Form("")) -> Response:
        admin = require_admin(request)
        changed = 0
        for submission_id in submission_ids:
            try:
                if action == "approve":
                    approve_submission(settings.db_path, submission_id)
                elif action == "reject":
                    reject_submission(settings.db_path, submission_id, reason.strip() or "Rejected by admin")
                elif action == "candidate":
                    set_submission_candidate(settings.db_path, submission_id, True)
                else:
                    continue
                changed += 1
            except GatewayStateError:
                continue
        audit(request, admin, f"submission.batch_{action}", "submission", "", f"changed={changed}")
        return redirect("/admin", notice=f"Batch updated {changed} submissions")

    @app.get("/admin/audit", response_class=HTMLResponse)
    def admin_audit(request: Request) -> HTMLResponse:
        require_admin(request)
        return templates.TemplateResponse(
            request,
            "admin_audit.html",
            base_context(request, logs=list_audit_logs(settings.db_path), notice=request.query_params.get("notice"), error=request.query_params.get("error")),
        )

    @app.get("/admin/health", response_class=HTMLResponse)
    def admin_health(request: Request) -> HTMLResponse:
        require_admin(request)
        vehicles = list_vehicles(settings.db_path)
        health = list_latest_vehicle_health(settings.db_path)
        for vehicle in vehicles:
            vehicle["health"] = health.get(int(vehicle["id"]))
        return templates.TemplateResponse(
            request,
            "admin_health.html",
            base_context(request, vehicles=vehicles, dispatches=list_dispatches(settings.db_path), notice=request.query_params.get("notice"), error=request.query_params.get("error")),
        )

    @app.get("/admin/status")
    def admin_status(request: Request) -> JSONResponse:
        require_admin(request)
        return JSONResponse(
            {
                "vehicles": list_vehicles(settings.db_path),
                "vehicle_health": list_latest_vehicle_health(settings.db_path),
                "dispatches": list_dispatches(settings.db_path),
            }
        )

    @app.post("/admin/vehicles/{vehicle_id}/preflight")
    def vehicle_preflight(request: Request, vehicle_id: int) -> Response:
        admin = require_admin(request)
        vehicle = get_vehicle(settings.db_path, vehicle_id)
        if vehicle is None:
            return redirect("/admin/health", error="Vehicle not found")
        codec = CredentialCodec(settings.credential_secret)
        console_status = "skipped"
        ssh_status = "skipped"
        rsync_status = "unknown"
        disk_free_bytes = None
        messages: list[str] = []
        if vehicle.get("console_url"):
            try:
                with VehicleClient(vehicle["console_url"], codec.decrypt(vehicle.get("console_password_encrypted")), timeout_seconds=settings.vehicle_timeout_seconds) as client:
                    client.login()
                    client.model_loading_status()
                console_status = "reachable"
            except (VehicleClientError, OSError) as exc:
                console_status = "failed"
                messages.append(f"console: {exc}")
        if vehicle.get("ssh_host") and vehicle.get("ssh_username"):
            try:
                client = SshDeliveryClient(
                    host=vehicle["ssh_host"],
                    port=int(vehicle["ssh_port"]),
                    username=vehicle["ssh_username"],
                    password=codec.decrypt(vehicle.get("ssh_password_encrypted")),
                    private_key_path=vehicle["ssh_private_key_path"],
                    host_key_sha256=vehicle.get("ssh_host_key_sha256") or "",
                    remote_artifact_root=vehicle["ssh_remote_artifact_root"],
                    timeout_seconds=settings.ssh_timeout_seconds,
                )
                result = client.preflight()
                ssh_status = str(result["ssh_status"])
                rsync_status = str(result["rsync_status"])
                disk_free_bytes = result.get("disk_free_bytes") if isinstance(result.get("disk_free_bytes"), int) else None
            except SshDeliveryError as exc:
                ssh_status = "failed"
                messages.append(f"ssh: {exc}")
        record_vehicle_health_check(
            settings.db_path,
            vehicle_id,
            console_status=console_status,
            ssh_status=ssh_status,
            rsync_status=rsync_status,
            disk_free_bytes=disk_free_bytes,
            message="; ".join(messages) or "Preflight completed",
        )
        audit(request, admin, "vehicle.preflight", "vehicle", vehicle_id, "; ".join(messages))
        return redirect("/admin/health", notice="Vehicle preflight completed")

    @app.get("/admin/events", response_class=HTMLResponse)
    def admin_events(request: Request) -> HTMLResponse:
        require_admin(request)
        return templates.TemplateResponse(
            request,
            "admin_events.html",
            base_context(
                request,
                events=list_events(settings.db_path),
                rounds=list_rounds(settings.db_path),
                notice=request.query_params.get("notice"),
                error=request.query_params.get("error"),
            ),
        )

    @app.get("/admin/rounds", response_class=HTMLResponse)
    def admin_rounds_alias(request: Request) -> Response:
        require_admin(request)
        return redirect("/admin/events")

    @app.post("/admin/events")
    def add_event(request: Request, name: str = Form(...), status: str = Form(EVENT_ACTIVE)) -> Response:
        admin = require_admin(request)
        try:
            event_id = create_event(settings.db_path, name, status=status)
            audit(request, admin, "event.create", "event", event_id, name)
            return redirect("/admin/events", notice="Event created")
        except (GatewayStateError, sqlite3.IntegrityError) as exc:
            return redirect("/admin/events", error=str(exc))

    @app.post("/admin/events/{event_id}/update")
    def edit_event(request: Request, event_id: int, name: str = Form(...), status: str = Form(EVENT_ACTIVE)) -> Response:
        admin = require_admin(request)
        try:
            update_event(settings.db_path, event_id, name=name, status=status)
            audit(request, admin, "event.update", "event", event_id, f"name={name} status={status}")
            return redirect("/admin/events", notice="Event updated")
        except (GatewayStateError, sqlite3.IntegrityError) as exc:
            return redirect("/admin/events", error=str(exc))

    @app.post("/admin/rounds")
    def add_round(
        request: Request,
        event_id: int = Form(...),
        name: str = Form(...),
        status: str = Form(ROUND_OPEN),
        upload_deadline_at: str = Form(""),
        max_submissions_per_team: str = Form(""),
        max_dispatches_per_team: str = Form(""),
    ) -> Response:
        admin = require_admin(request)
        try:
            round_id = create_round(
                settings.db_path,
                event_id,
                name,
                status=status,
                upload_deadline_at=upload_deadline_at,
                max_submissions_per_team=_optional_int(max_submissions_per_team),
                max_dispatches_per_team=_optional_int(max_dispatches_per_team),
            )
            audit(request, admin, "round.create", "round", round_id, name)
            return redirect("/admin/events", notice="Round created")
        except (GatewayStateError, sqlite3.IntegrityError) as exc:
            return redirect("/admin/events", error=str(exc))

    @app.post("/admin/rounds/{round_id}/update")
    def edit_round(
        request: Request,
        round_id: int,
        event_id: int = Form(...),
        name: str = Form(...),
        status: str = Form(ROUND_OPEN),
        upload_deadline_at: str = Form(""),
        max_submissions_per_team: str = Form(""),
        max_dispatches_per_team: str = Form(""),
    ) -> Response:
        admin = require_admin(request)
        try:
            update_round(
                settings.db_path,
                round_id,
                event_id=event_id,
                name=name,
                status=status,
                upload_deadline_at=upload_deadline_at,
                max_submissions_per_team=_optional_int(max_submissions_per_team),
                max_dispatches_per_team=_optional_int(max_dispatches_per_team),
            )
            audit(request, admin, "round.update", "round", round_id, f"name={name} status={status}")
            return redirect("/admin/events", notice="Round updated")
        except (GatewayStateError, sqlite3.IntegrityError) as exc:
            return redirect("/admin/events", error=str(exc))

    @app.get("/admin/export/users")
    def export_users(request: Request) -> Response:
        require_admin(request)
        return _csv_response(
            [("id", "username", "display_name", "role", "status", "team_name")]
            + [(u["id"], u["username"], u["display_name"], u["role"], u["status"], u.get("team_name") or "") for u in list_users(settings.db_path)],
            "users.csv",
        )

    @app.get("/admin/export/teams")
    def export_teams(request: Request) -> Response:
        require_admin(request)
        return _csv_response(
            [("id", "name", "join_code", "status", "member_count", "max_members")]
            + [(t["id"], t["name"], t["join_code"], t["status"], t["member_count"], t.get("max_members") or "") for t in list_teams(settings.db_path)],
            "teams.csv",
        )

    @app.get("/admin/export/submissions")
    def export_submissions(request: Request) -> Response:
        require_admin(request)
        return _csv_response(
            [("id", "round", "team", "user", "model", "version", "candidate", "status", "sha256", "created_at")]
            + [
                (
                    s["id"],
                    s.get("round_name") or "",
                    s["team_name_snapshot"],
                    s["username_snapshot"],
                    s["model_name"],
                    s.get("version_number") or "",
                    s.get("is_candidate") or 0,
                    s["status"],
                    s["sha256"],
                    s["created_at"],
                )
                for s in list_submissions(settings.db_path)
            ],
            "submissions.csv",
        )

    @app.get("/admin/export/dispatches")
    def export_dispatches(request: Request) -> Response:
        require_admin(request)
        return _csv_response(
            [("id", "vehicle", "model", "mode", "status", "message", "updated_at")]
            + [(d["id"], d["vehicle_name"], d["model_name"], d["requested_mode"], d["status"], d["message"], d["updated_at"]) for d in list_dispatches(settings.db_path, limit=1000)],
            "dispatches.csv",
        )

    @app.get("/admin/dispatches/{dispatch_id}")
    def dispatch_status(request: Request, dispatch_id: int) -> JSONResponse:
        require_admin(request)
        dispatch_row = get_dispatch(settings.db_path, dispatch_id)
        if dispatch_row is None:
            raise HTTPException(status_code=404, detail="Dispatch not found")
        dispatch_row["attempts"] = list_dispatch_attempts(settings.db_path, dispatch_id)
        return JSONResponse(dispatch_row)

    return app


def get_user_team_for_app(db_path: Path, user_id: int) -> dict | None:
    from model_gateway.database import get_user_team

    return get_user_team(db_path, user_id)


def _team_for_import(db_path: Path, team_name: str) -> int:
    existing = get_team_by_name(db_path, team_name)
    if existing is not None:
        return int(existing["id"])
    return create_team(db_path, team_name)


def _optional_int(value: str | int | None) -> int | None:
    if value is None or value == "":
        return None
    parsed = int(value)
    return parsed if parsed > 0 else None


def _csv_response(rows: list[tuple[object, ...]], filename: str) -> Response:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerows(rows)
    return Response(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


app = create_app()
