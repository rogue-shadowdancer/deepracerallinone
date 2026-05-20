from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from model_gateway.config import Settings
from model_gateway.database import (
    ROLE_USER,
    SETTING_REGISTRATION_ENABLED,
    USER_ACTIVE,
    create_team,
    create_user,
    get_team,
    get_vehicle,
    get_user_by_username,
    join_team,
    list_submissions,
    list_vehicles,
    set_setting,
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
        data={"username": "newbie", "display_name": "Newbie", "password": "pw"},
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
