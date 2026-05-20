from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from model_gateway.app import CSRF_COOKIE_NAME, create_app
from model_gateway.config import Settings
from model_gateway.database import (
    ROLE_USER,
    SETTING_REGISTRATION_ENABLED,
    USER_ACTIVE,
    approve_submission,
    create_dispatch_if_available,
    create_team,
    create_user,
    create_vehicle,
    get_team,
    get_dispatch,
    get_vehicle,
    get_user_by_username,
    join_team,
    list_backups,
    list_audit_logs,
    list_vehicle_diagnostics,
    list_submissions,
    list_vehicles,
    set_setting,
    update_dispatch_status,
)

from conftest import make_model_tar


def _login_admin(client: TestClient) -> None:
    response = client.post("/admin/login", data={"username": "admin", "password": "test-admin"}, follow_redirects=False)
    assert response.status_code == 303


def _seed_user_team(settings: Settings) -> tuple[int, int]:
    user_id = create_user(settings.db_path, "ada", "Ada", "pw", role=ROLE_USER, status=USER_ACTIVE)
    team_id = create_team(settings.db_path, "Team A", leader_user_id=user_id)
    return user_id, team_id


def _login_user(client: TestClient) -> None:
    response = client.post("/login", data={"username": "ada", "password": "pw"}, follow_redirects=False)
    assert response.status_code == 303


def test_upload_requires_login(client: TestClient) -> None:
    response = client.get("/upload", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_regular_user_cannot_access_admin(client: TestClient, settings: Settings) -> None:
    _seed_user_team(settings)
    _login_user(client)

    response = client.get("/admin", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_upload_creates_submission_with_user_and_team(client: TestClient, settings: Settings, tmp_path: Path) -> None:
    user_id, team_id = _seed_user_team(settings)
    _login_user(client)
    archive = make_model_tar(tmp_path / "physicalmodel-team.tar.gz")

    with archive.open("rb") as model_file:
        response = client.post(
            "/upload",
            data={"model_name": "Fast model", "notes": "Round 1"},
            files={"file": ("physicalmodel-team.tar.gz", model_file, "application/gzip")},
        )

    assert response.status_code == 200
    assert "Submission received" in response.text
    submissions = list_submissions(settings.db_path)
    assert len(submissions) == 1
    assert submissions[0]["user_id"] == user_id
    assert submissions[0]["team_id"] == team_id
    assert submissions[0]["team_name_snapshot"] == "Team A"
    assert submissions[0]["status"] == "uploaded"


def test_upload_rejects_oversized_file(client: TestClient, settings: Settings, tmp_path: Path) -> None:
    _seed_user_team(settings)
    _login_user(client)
    archive = tmp_path / "large.tar.gz"
    archive.write_bytes(b"x" * (1024 * 1024 + 1))

    with archive.open("rb") as model_file:
        response = client.post(
            "/upload",
            data={"model_name": "Large", "notes": ""},
            files={"file": ("large.tar.gz", model_file, "application/gzip")},
        )

    assert response.status_code == 400
    assert "upload size limit" in response.text


def test_admin_login_approve_and_vehicle_registration(client: TestClient, settings: Settings, tmp_path: Path) -> None:
    _seed_user_team(settings)
    _login_user(client)
    archive = make_model_tar(tmp_path / "model.tar.gz")
    with archive.open("rb") as model_file:
        client.post(
            "/upload",
            data={"model_name": "Model", "notes": ""},
            files={"file": ("model.tar.gz", model_file, "application/gzip")},
        )
    submission_id = list_submissions(settings.db_path)[0]["id"]

    _login_admin(client)
    vehicle_response = client.post(
        "/admin/vehicles",
        data={
            "name": "Car 1",
            "console_url": "http://car.local",
            "console_password": "pw",
            "delivery_mode": "auto",
            "ssh_port": "22",
            "ssh_remote_artifact_root": "/opt/aws/deepracer/artifacts",
        },
        follow_redirects=False,
    )
    assert vehicle_response.status_code == 303
    assert list_vehicles(settings.db_path)[0]["has_console_password"]

    approve_response = client.post(f"/admin/submissions/{submission_id}/approve", follow_redirects=False)
    assert approve_response.status_code == 303
    assert list_submissions(settings.db_path)[0]["status"] == "approved"


def test_admin_user_batch_and_registration_toggle(client: TestClient, settings: Settings) -> None:
    _login_admin(client)
    response = client.post(
        "/admin/settings/registration",
        data={"registration_enabled": "true", "default_team_max_members": "3"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    register = client.post(
        "/register",
        data={"username": "newbie", "display_name": "Newbie", "password": "newbie-password"},
        follow_redirects=False,
    )
    assert register.status_code == 303
    assert get_user_by_username(settings.db_path, "newbie")["status"] == "pending"

    batch = client.post("/admin/users/batch", data={"prefix": "racer", "count": "2", "team_name": "Batch Team"})
    assert batch.status_code == 200
    assert "racer001" in batch.text


def test_admin_vehicle_update_route_preserves_and_clears_credentials(client: TestClient, settings: Settings) -> None:
    _login_admin(client)
    client.post(
        "/admin/vehicles",
        data={
            "name": "Car 1",
            "console_url": "http://car.local",
            "console_password": "console",
            "delivery_mode": "auto",
            "ssh_host": "car.local",
            "ssh_port": "22",
            "ssh_username": "ubuntu",
            "ssh_password": "ssh",
            "ssh_remote_artifact_root": "/opt/aws/deepracer/artifacts",
        },
    )
    vehicle_id = list_vehicles(settings.db_path)[0]["id"]

    response = client.post(
        f"/admin/vehicles/{vehicle_id}/update",
        data={
            "name": "Car 2",
            "console_url": "http://car2.local",
            "delivery_mode": "ssh",
            "ssh_host": "car2.local",
            "ssh_port": "2200",
            "ssh_username": "deepracer",
            "ssh_private_key_path": "C:/keys/car.pem",
            "ssh_remote_artifact_root": "/models",
            "ssh_install_command_template": "echo {model_dir}",
            "notes": "updated",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    vehicle = get_vehicle(settings.db_path, vehicle_id)
    assert vehicle["name"] == "Car 2"
    assert vehicle["delivery_mode"] == "ssh"
    assert vehicle["ssh_port"] == 2200
    assert vehicle["has_console_password"]
    assert vehicle["has_ssh_password"]

    client.post(
        f"/admin/vehicles/{vehicle_id}/update",
        data={
            "name": "Car 2",
            "console_url": "http://car2.local",
            "delivery_mode": "ssh",
            "clear_console_password": "true",
            "clear_ssh_password": "true",
            "ssh_port": "22",
            "ssh_remote_artifact_root": "/opt/aws/deepracer/artifacts",
        },
    )
    vehicle = get_vehicle(settings.db_path, vehicle_id)
    assert not vehicle["has_console_password"]
    assert not vehicle["has_ssh_password"]


def test_admin_user_update_route_and_last_admin_protection(client: TestClient, settings: Settings) -> None:
    _login_admin(client)
    user_id = create_user(settings.db_path, "racer", "Racer", "pw", role=ROLE_USER, status=USER_ACTIVE)
    team_id = create_team(settings.db_path, "Editable Team")

    response = client.post(
        f"/admin/users/{user_id}/update",
        data={
            "username": "pilot",
            "display_name": "Pilot",
            "role": "user",
            "status": "active",
            "team_id": str(team_id),
            "team_role": "leader",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert get_user_by_username(settings.db_path, "pilot")["display_name"] == "Pilot"
    assert get_team(settings.db_path, team_id)["members"][0]["role"] == "leader"

    admin = get_user_by_username(settings.db_path, "admin")
    response = client.post(
        f"/admin/users/{admin['id']}/update",
        data={
            "username": "admin",
            "display_name": "Admin",
            "role": "user",
            "status": "active",
            "team_id": "",
            "team_role": "member",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "last+active+admin" in response.headers["location"]


def test_admin_team_member_routes(client: TestClient, settings: Settings) -> None:
    _login_admin(client)
    user_id = create_user(settings.db_path, "racer", "Racer", "pw", role=ROLE_USER, status=USER_ACTIVE)
    team_id = create_team(settings.db_path, "Team", max_members=2)
    join_team(settings.db_path, team_id, user_id)
    old_code = get_team(settings.db_path, team_id)["join_code"]

    response = client.post(f"/admin/teams/{team_id}/regenerate-code", follow_redirects=False)
    assert response.status_code == 303
    assert get_team(settings.db_path, team_id)["join_code"] != old_code

    response = client.post(
        f"/admin/teams/{team_id}/members/{user_id}/role",
        data={"role": "leader"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert get_team(settings.db_path, team_id)["members"][0]["role"] == "leader"

    response = client.post(f"/admin/teams/{team_id}/members/{user_id}/remove", follow_redirects=False)
    assert response.status_code == 303
    assert get_team(settings.db_path, team_id)["member_count"] == 0


def test_csrf_required_for_post(settings: Settings) -> None:
    raw_client = TestClient(create_app(settings))

    response = raw_client.post("/admin/login", data={"username": "admin", "password": "test-admin"}, follow_redirects=False)
    assert response.status_code == 403

    raw_client.get("/admin/login")
    token = raw_client.cookies.get(CSRF_COOKIE_NAME)
    query_response = raw_client.post(
        f"/admin/login?csrf_token={token}",
        data={"username": "admin", "password": "test-admin"},
        follow_redirects=False,
    )
    assert query_response.status_code == 403
    response = raw_client.post(
        "/admin/login",
        data={"username": "admin", "password": "test-admin"},
        headers={"x-csrf-token": token},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_login_rate_limit_and_audit(client: TestClient, settings: Settings) -> None:
    _login_admin(client)
    client.post("/admin/users", data={"username": "audituser", "display_name": "Audit User", "role": "user", "status": "active"})

    for _ in range(settings.login_rate_limit):
        response = client.post("/admin/login", data={"username": "admin", "password": "wrong"}, follow_redirects=False)
        assert response.status_code == 303

    locked = client.post("/admin/login", data={"username": "admin", "password": "test-admin"}, follow_redirects=False)
    assert "Too+many+failed" in locked.headers["location"]

    actions = [row["action"] for row in list_audit_logs(settings.db_path)]
    assert "admin.login" in actions
    assert "user.create" in actions
    assert "auth.locked" in actions


def test_events_rounds_exports_and_upload_binding(client: TestClient, settings: Settings, tmp_path: Path) -> None:
    _seed_user_team(settings)
    _login_admin(client)
    event_response = client.post("/admin/events", data={"name": "Race Day", "status": "active"}, follow_redirects=False)
    assert event_response.status_code == 303
    round_response = client.post(
        "/admin/rounds",
        data={
            "event_id": "2",
            "name": "Round 1",
            "status": "open",
            "max_submissions_per_team": "2",
            "max_dispatches_per_team": "1",
        },
        follow_redirects=False,
    )
    assert round_response.status_code == 303

    _login_user(client)
    archive = make_model_tar(tmp_path / "round-model.tar.gz")
    with archive.open("rb") as model_file:
        upload = client.post(
            "/upload",
            data={"model_name": "Round Model", "notes": ""},
            files={"file": ("round-model.tar.gz", model_file, "application/gzip")},
        )

    assert upload.status_code == 200
    submission = list_submissions(settings.db_path)[0]
    assert submission["round_name"] == "Round 1"
    assert submission["version_number"] == 1
    export = client.get("/admin/export/submissions")
    assert "Round 1" in export.text


def test_admin_backup_and_support_bundle_routes(client: TestClient, settings: Settings) -> None:
    _login_admin(client)

    backup_response = client.post("/admin/backups", data={"reason": "test"}, follow_redirects=False)
    assert backup_response.status_code == 303
    backups = list_backups(settings.db_path)
    assert len(backups) == 1

    page = client.get("/admin/backups")
    assert "Existing backups" in page.text
    download = client.get(f"/admin/backups/{backups[0]['id']}/download")
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/gzip"

    bundle = client.get("/admin/support-bundle")
    assert bundle.status_code == 200
    assert bundle.headers["content-type"] == "application/gzip"
    assert b"test-credential-secret" not in bundle.content


def test_admin_dispatch_timeline_and_retry(client: TestClient, settings: Settings, tmp_path: Path) -> None:
    user_id, team_id = _seed_user_team(settings)
    archive = make_model_tar(tmp_path / "retry.tar.gz")
    submission_id = list_submissions(settings.db_path)[0]["id"] if list_submissions(settings.db_path) else None
    if submission_id is None:
        from model_gateway.database import NewSubmission, create_submission

        submission_id = create_submission(
            settings.db_path,
            NewSubmission(
                user_id=user_id,
                team_id=team_id,
                username_snapshot="ada",
                display_name_snapshot="Ada",
                team_name_snapshot="Team A",
                team_members_snapshot="[]",
                model_name="Retry Model",
                notes="",
                original_filename="retry.tar.gz",
                storage_path=str(archive),
                sha256="abc",
                size_bytes=archive.stat().st_size,
            ),
        )
    approve_submission(settings.db_path, int(submission_id))
    vehicle_id = create_vehicle(settings.db_path, "Retry Car", "http://car.local", None)
    dispatch_id = create_dispatch_if_available(settings.db_path, int(submission_id), vehicle_id)
    update_dispatch_status(settings.db_path, dispatch_id, "failed", "network")

    _login_admin(client)
    timeline = client.get(f"/admin/dispatches/{dispatch_id}/timeline")
    assert timeline.status_code == 200
    assert "Retry dispatch" in timeline.text

    retry_response = client.post(f"/admin/dispatches/{dispatch_id}/retry", follow_redirects=False)
    assert retry_response.status_code == 303
    assert get_dispatch(settings.db_path, dispatch_id)["status"] == "queued"


def test_admin_vehicle_diagnostics_route_records_result(client: TestClient, settings: Settings) -> None:
    _login_admin(client)
    vehicle_id = create_vehicle(settings.db_path, "Diag Car", "", None)

    response = client.post(f"/admin/vehicles/{vehicle_id}/diagnostics", follow_redirects=False)

    assert response.status_code == 303
    diagnostics = list_vehicle_diagnostics(settings.db_path, vehicle_id)
    assert diagnostics
    assert diagnostics[0]["overall_status"] == "warning"
    page = client.get(f"/admin/vehicles/{vehicle_id}/diagnostics")
    assert "Vehicle diagnostics" in page.text
