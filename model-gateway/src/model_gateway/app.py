from __future__ import annotations

import hmac
import hashlib
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlencode

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from model_gateway.config import Settings
from model_gateway.database import (
    GatewayStateError,
    NewSubmission,
    VehicleBusyError,
    approve_submission,
    create_dispatch_if_available,
    create_submission,
    create_vehicle,
    get_dispatch,
    init_db,
    list_dispatches,
    list_submissions,
    list_vehicles,
    reject_submission,
)
from model_gateway.dispatch import dispatch_model_to_vehicle
from model_gateway.storage import UploadValidationError, save_upload


PACKAGE_DIR = Path(__file__).parent
COOKIE_NAME = "model_gateway_admin"
COOKIE_VALUE = "admin"


def sign_cookie(value: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{value}.{digest}"


def verify_cookie(signed_value: str | None, secret: str) -> bool:
    if not signed_value or "." not in signed_value:
        return False
    value, digest = signed_value.rsplit(".", 1)
    expected = hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()
    return value == COOKIE_VALUE and hmac.compare_digest(digest, expected)


def create_app(settings: Settings | None = None) -> FastAPI:
    explicit_settings = settings is not None
    settings = settings or Settings()

    def initialize_storage() -> None:
        settings.ensure_directories()
        init_db(settings.db_path)

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

    def is_admin(request: Request) -> bool:
        return verify_cookie(request.cookies.get(COOKIE_NAME), settings.session_secret)

    def admin_redirect() -> RedirectResponse:
        return RedirectResponse("/admin/login", status_code=303)

    def admin_url(**params: str) -> str:
        return "/admin?" + urlencode(params)

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> RedirectResponse:
        if is_admin(request):
            return RedirectResponse("/admin", status_code=303)
        return RedirectResponse("/upload", status_code=303)

    @app.get("/upload", response_class=HTMLResponse)
    def upload_form(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "upload.html", {})

    @app.post("/upload", response_class=HTMLResponse)
    async def upload_model(
        request: Request,
        team_name: str = Form(...),
        racer_name: str = Form(...),
        model_name: str = Form(...),
        notes: str = Form(""),
        file: UploadFile = File(...),
    ) -> HTMLResponse:
        try:
            stored = await save_upload(file, settings.upload_dir, settings.max_upload_bytes)
            submission = NewSubmission(
                team_name=team_name.strip(),
                racer_name=racer_name.strip(),
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
                {"error": str(exc), "team_name": team_name, "racer_name": racer_name, "model_name": model_name, "notes": notes},
                status_code=400,
            )
        return templates.TemplateResponse(
            request,
            "upload_success.html",
            {
                "submission_id": submission_id,
                "model_name": model_name,
                "warning": stored.warning,
            },
        )

    @app.get("/admin/login", response_class=HTMLResponse)
    def admin_login_form(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "admin_login.html", {})

    @app.post("/admin/login")
    def admin_login(password: str = Form(...)) -> Response:
        if not hmac.compare_digest(password, settings.admin_password):
            return RedirectResponse("/admin/login?error=1", status_code=303)
        response = RedirectResponse("/admin", status_code=303)
        response.set_cookie(
            COOKIE_NAME,
            sign_cookie(COOKIE_VALUE, settings.session_secret),
            httponly=True,
            samesite="lax",
        )
        return response

    @app.post("/admin/logout")
    def admin_logout() -> Response:
        response = RedirectResponse("/upload", status_code=303)
        response.delete_cookie(COOKIE_NAME)
        return response

    @app.get("/admin", response_class=HTMLResponse)
    def admin_dashboard(request: Request) -> Response:
        if not is_admin(request):
            return admin_redirect()
        return templates.TemplateResponse(
            request,
            "admin.html",
            {
                "submissions": list_submissions(settings.db_path),
                "vehicles": list_vehicles(settings.db_path),
                "dispatches": list_dispatches(settings.db_path),
                "notice": request.query_params.get("notice"),
                "error": request.query_params.get("error"),
            },
        )

    @app.post("/admin/vehicles")
    def add_vehicle(
        request: Request,
        name: str = Form(...),
        console_url: str = Form(...),
        console_password: str = Form(""),
    ) -> Response:
        if not is_admin(request):
            return admin_redirect()
        if not console_url.startswith(("http://", "https://")):
            return RedirectResponse(admin_url(error="Vehicle URL must start with http:// or https://"), status_code=303)
        create_vehicle(settings.db_path, name.strip(), console_url.strip(), console_password.strip() or None)
        return RedirectResponse(admin_url(notice="Vehicle saved"), status_code=303)

    @app.post("/admin/submissions/{submission_id}/approve")
    def approve(request: Request, submission_id: int) -> Response:
        if not is_admin(request):
            return admin_redirect()
        try:
            approve_submission(settings.db_path, submission_id)
            return RedirectResponse(admin_url(notice="Submission approved"), status_code=303)
        except GatewayStateError as exc:
            return RedirectResponse(admin_url(error=str(exc)), status_code=303)

    @app.post("/admin/submissions/{submission_id}/reject")
    def reject(request: Request, submission_id: int, reason: str = Form("")) -> Response:
        if not is_admin(request):
            return admin_redirect()
        try:
            reject_submission(settings.db_path, submission_id, reason.strip() or "Rejected by admin")
            return RedirectResponse(admin_url(notice="Submission rejected"), status_code=303)
        except GatewayStateError as exc:
            return RedirectResponse(admin_url(error=str(exc)), status_code=303)

    @app.post("/admin/submissions/{submission_id}/dispatch")
    def dispatch(
        request: Request,
        background_tasks: BackgroundTasks,
        submission_id: int,
        vehicle_id: int = Form(...),
    ) -> Response:
        if not is_admin(request):
            return admin_redirect()
        try:
            dispatch_id = create_dispatch_if_available(settings.db_path, submission_id, vehicle_id)
        except VehicleBusyError as exc:
            return RedirectResponse(admin_url(error=str(exc)), status_code=303)
        except GatewayStateError as exc:
            return RedirectResponse(admin_url(error=str(exc)), status_code=303)
        background_tasks.add_task(dispatch_model_to_vehicle, settings, dispatch_id)
        return RedirectResponse(admin_url(notice=f"Dispatch {dispatch_id} started"), status_code=303)

    @app.get("/admin/dispatches/{dispatch_id}")
    def dispatch_status(request: Request, dispatch_id: int) -> JSONResponse:
        if not is_admin(request):
            raise HTTPException(status_code=401, detail="Admin login required")
        dispatch_row = get_dispatch(settings.db_path, dispatch_id)
        if dispatch_row is None:
            raise HTTPException(status_code=404, detail="Dispatch not found")
        return JSONResponse(dispatch_row)

    return app


app = create_app()
