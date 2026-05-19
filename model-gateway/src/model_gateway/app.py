from __future__ import annotations

import csv
import io
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlencode

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from model_gateway.config import Settings
from model_gateway.database import (
    DISPATCH_MODE_AUTO,
    DISPATCH_MODE_CONSOLE_API,
    DISPATCH_MODE_SSH,
    GatewayStateError,
    NewSubmission,
    ROLE_ADMIN,
    ROLE_USER,
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
    create_dispatch_if_available,
    create_session,
    create_submission,
    create_team,
    create_user,
    create_vehicle,
    default_team_max_members,
    disable_user,
    ensure_bootstrap_admin,
    get_dispatch,
    get_setting,
    get_team_by_name,
    get_user,
    get_user_by_session,
    init_db,
    is_registration_enabled,
    join_team,
    join_team_by_code,
    leave_team,
    list_dispatch_attempts,
    list_dispatches,
    list_sessions,
    list_submissions,
    list_teams,
    list_users,
    list_vehicles,
    move_user_to_team,
    reject_submission,
    reset_user_password,
    revoke_session,
    revoke_session_by_id,
    set_setting,
    team_members_snapshot,
    update_team,
)
from model_gateway.dispatch import dispatch_model_to_vehicle
from model_gateway.security import CredentialCodec, generate_password
from model_gateway.ssh_delivery import SshDeliveryClient, SshDeliveryError
from model_gateway.storage import UploadValidationError, save_upload
from model_gateway.vehicle import VehicleClient, VehicleClientError


PACKAGE_DIR = Path(__file__).parent
USER_COOKIE_NAME = "model_gateway_user_session"
ADMIN_COOKIE_NAME = "model_gateway_admin_session"


def create_app(settings: Settings | None = None) -> FastAPI:
    explicit_settings = settings is not None
    settings = settings or Settings()

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
            initialize_storage()
            yield

        app = FastAPI(title="DeepRacer Model Gateway", lifespan=lifespan)

    app.state.settings = settings
    templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))
    app.mount("/static", StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static")

    def user_from_request(request: Request) -> dict | None:
        return get_user_by_session(settings.db_path, request.cookies.get(USER_COOKIE_NAME), role=ROLE_USER)

    def admin_from_request(request: Request) -> dict | None:
        return get_user_by_session(settings.db_path, request.cookies.get(ADMIN_COOKIE_NAME), role=ROLE_ADMIN)

    def redirect(url: str, **params: str) -> RedirectResponse:
        if params:
            url += "?" + urlencode(params)
        return RedirectResponse(url, status_code=303)

    def set_session_cookie(response: Response, name: str, token: str) -> None:
        response.set_cookie(name, token, httponly=True, samesite="lax")

    def base_context(request: Request, **context: object) -> dict[str, object]:
        return {
            "request": request,
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

        user = authenticate_user(settings.db_path, username, password, role=ROLE_USER)
        if user is None:
            return redirect("/login", error="Invalid username, password, or account status")
        token = create_session(settings.db_path, int(user["id"]), request.headers.get("user-agent", ""))
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
            create_user(settings.db_path, username, display_name, password, role=ROLE_USER, status=USER_PENDING)
            return redirect("/login", notice="Registration submitted. Wait for admin approval.")
        except (GatewayStateError, sqlite3.IntegrityError) as exc:
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
        return templates.TemplateResponse(request, "upload.html", base_context(request, user=user, team=team))

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
            stored = await save_upload(file, settings.upload_dir, settings.max_upload_bytes)
            submission = NewSubmission(
                user_id=int(user["id"]),
                team_id=int(team["id"]),
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
        except UploadValidationError as exc:
            return templates.TemplateResponse(
                request,
                "upload.html",
                base_context(request, user=user, team=team, error=str(exc), model_name=model_name, notes=notes),
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

        admin = authenticate_user(settings.db_path, username, password, role=ROLE_ADMIN)
        if admin is None:
            return redirect("/admin/login", error="Invalid admin username, password, or account status")
        token = create_session(settings.db_path, int(admin["id"]), request.headers.get("user-agent", ""))
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
        return templates.TemplateResponse(
            request,
            "admin.html",
            base_context(
                request,
                submissions=list_submissions(settings.db_path),
                vehicles=list_vehicles(settings.db_path),
                dispatches=list_dispatches(settings.db_path),
                notice=request.query_params.get("notice"),
                error=request.query_params.get("error"),
            ),
        )

    @app.get("/admin/users", response_class=HTMLResponse)
    def admin_users(request: Request) -> HTMLResponse:
        require_admin(request)
        return templates.TemplateResponse(
            request,
            "admin_users.html",
            base_context(
                request,
                users=list_users(settings.db_path),
                sessions=list_sessions(settings.db_path),
                teams=list_teams(settings.db_path),
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
        require_admin(request)
        password = password or generate_password()
        try:
            create_user(settings.db_path, username, display_name or username, password, role=role, status=status)
            return redirect("/admin/users", generated=f"{username},{password}")
        except (GatewayStateError, sqlite3.IntegrityError) as exc:
            return redirect("/admin/users", error=str(exc))

    @app.post("/admin/users/batch")
    def admin_batch_users(request: Request, prefix: str = Form("racer"), count: int = Form(...), team_name: str = Form("")) -> Response:
        require_admin(request)
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
        return _csv_response(rows, "generated-users.csv")

    @app.post("/admin/users/import")
    async def admin_import_users(request: Request, file: UploadFile = File(...)) -> Response:
        require_admin(request)
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
                user_id = create_user(settings.db_path, username, display_name, password, role=ROLE_USER, status=USER_ACTIVE)
                if team_name:
                    join_team(settings.db_path, _team_for_import(settings.db_path, team_name), user_id)
                rows.append((username, display_name, team_name, password))
            except (GatewayStateError, sqlite3.IntegrityError):
                continue
        return _csv_response(rows, "imported-users.csv")

    @app.post("/admin/users/{user_id}/approve")
    def admin_approve_user(request: Request, user_id: int) -> Response:
        require_admin(request)
        approve_user(settings.db_path, user_id)
        return redirect("/admin/users", notice="User approved")

    @app.post("/admin/users/{user_id}/disable")
    def admin_disable_user(request: Request, user_id: int) -> Response:
        require_admin(request)
        disable_user(settings.db_path, user_id)
        return redirect("/admin/users", notice="User disabled")

    @app.post("/admin/users/{user_id}/reset-password")
    def admin_reset_password(request: Request, user_id: int) -> Response:
        require_admin(request)
        password = reset_user_password(settings.db_path, user_id)
        user = get_user(settings.db_path, user_id)
        return redirect("/admin/users", generated=f"{user['username'] if user else user_id},{password}")

    @app.post("/admin/sessions/{session_id}/revoke")
    def admin_revoke_session(request: Request, session_id: int) -> Response:
        require_admin(request)
        revoke_session_by_id(settings.db_path, session_id)
        return redirect("/admin/users", notice="Session revoked")

    @app.get("/admin/teams", response_class=HTMLResponse)
    def admin_teams(request: Request) -> HTMLResponse:
        require_admin(request)
        return templates.TemplateResponse(
            request,
            "admin_teams.html",
            base_context(
                request,
                teams=list_teams(settings.db_path),
                users=list_users(settings.db_path),
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
            create_team(settings.db_path, name, created_by_user_id=int(admin["id"]), max_members=_optional_int(max_members))
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
        require_admin(request)
        try:
            update_team(settings.db_path, team_id, name=name, max_members=_optional_int(max_members), status=status)
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
        require_admin(request)
        try:
            move_user_to_team(settings.db_path, user_id, team_id, role=role)
            return redirect("/admin/teams", notice="Team member updated")
        except GatewayStateError as exc:
            return redirect("/admin/teams", error=str(exc))

    @app.post("/admin/settings/registration")
    def admin_registration_settings(
        request: Request,
        registration_enabled: str = Form("false"),
        default_team_max_members: str = Form(""),
    ) -> Response:
        require_admin(request)
        set_setting(settings.db_path, SETTING_REGISTRATION_ENABLED, "true" if registration_enabled == "true" else "false")
        set_setting(settings.db_path, SETTING_DEFAULT_TEAM_MAX_MEMBERS, default_team_max_members.strip())
        return redirect("/admin/teams", notice="Settings saved")

    @app.get("/admin/vehicles", response_class=HTMLResponse)
    def admin_vehicles(request: Request) -> HTMLResponse:
        require_admin(request)
        return templates.TemplateResponse(
            request,
            "admin_vehicles.html",
            base_context(
                request,
                vehicles=list_vehicles(settings.db_path),
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
        ssh_remote_artifact_root: str = Form("/opt/aws/deepracer/artifacts"),
        ssh_install_command_template: str = Form(""),
        notes: str = Form(""),
    ) -> Response:
        require_admin(request)
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
                ssh_remote_artifact_root=ssh_remote_artifact_root,
                ssh_install_command_template=ssh_install_command_template,
                notes=notes,
            )
            return redirect("/admin/vehicles", notice="Vehicle saved")
        except GatewayStateError as exc:
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
                timeout_seconds=settings.ssh_timeout_seconds,
            )
            client._exec("true")
            return redirect("/admin/vehicles", notice="SSH reachable")
        except SshDeliveryError as exc:
            return redirect("/admin/vehicles", error=str(exc))

    @app.post("/admin/submissions/{submission_id}/approve")
    def approve(request: Request, submission_id: int) -> Response:
        require_admin(request)
        try:
            approve_submission(settings.db_path, submission_id)
            return redirect("/admin", notice="Submission approved")
        except GatewayStateError as exc:
            return redirect("/admin", error=str(exc))

    @app.post("/admin/submissions/{submission_id}/reject")
    def reject(request: Request, submission_id: int, reason: str = Form("")) -> Response:
        require_admin(request)
        try:
            reject_submission(settings.db_path, submission_id, reason.strip() or "Rejected by admin")
            return redirect("/admin", notice="Submission rejected")
        except GatewayStateError as exc:
            return redirect("/admin", error=str(exc))

    @app.post("/admin/submissions/{submission_id}/dispatch")
    def dispatch(
        request: Request,
        background_tasks: BackgroundTasks,
        submission_id: int,
        vehicle_id: int = Form(...),
        requested_mode: str = Form(DISPATCH_MODE_AUTO),
    ) -> Response:
        require_admin(request)
        try:
            dispatch_id = create_dispatch_if_available(settings.db_path, submission_id, vehicle_id, requested_mode=requested_mode)
        except GatewayStateError as exc:
            return redirect("/admin", error=str(exc))
        background_tasks.add_task(dispatch_model_to_vehicle, settings, dispatch_id)
        return redirect("/admin", notice=f"Dispatch {dispatch_id} started")

    @app.post("/admin/dispatches/{dispatch_id}/cancel")
    def cancel_dispatch_route(request: Request, dispatch_id: int) -> Response:
        require_admin(request)
        try:
            cancel_dispatch(settings.db_path, dispatch_id)
            return redirect("/admin", notice="Dispatch cancellation recorded")
        except GatewayStateError as exc:
            return redirect("/admin", error=str(exc))

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
