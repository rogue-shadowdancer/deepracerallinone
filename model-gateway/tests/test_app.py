from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from model_gateway.database import approve_submission, create_vehicle, list_submissions
from model_gateway.config import Settings

from conftest import make_model_tar


def test_upload_creates_submission(client: TestClient, settings: Settings, tmp_path: Path) -> None:
    archive = make_model_tar(tmp_path / "physicalmodel-team.tar.gz")

    with archive.open("rb") as model_file:
        response = client.post(
            "/upload",
            data={"team_name": "Team A", "racer_name": "Ada", "model_name": "Fast model", "notes": "Round 1"},
            files={"file": ("physicalmodel-team.tar.gz", model_file, "application/gzip")},
        )

    assert response.status_code == 200
    assert "Submission received" in response.text
    submissions = list_submissions(settings.db_path)
    assert len(submissions) == 1
    assert submissions[0]["team_name"] == "Team A"
    assert submissions[0]["status"] == "uploaded"


def test_upload_rejects_oversized_file(client: TestClient, tmp_path: Path) -> None:
    archive = tmp_path / "large.tar.gz"
    archive.write_bytes(b"x" * (1024 * 1024 + 1))

    with archive.open("rb") as model_file:
        response = client.post(
            "/upload",
            data={"team_name": "Team A", "racer_name": "Ada", "model_name": "Large", "notes": ""},
            files={"file": ("large.tar.gz", model_file, "application/gzip")},
        )

    assert response.status_code == 400
    assert "upload size limit" in response.text


def test_admin_login_approve_and_vehicle_registration(client: TestClient, settings: Settings, tmp_path: Path) -> None:
    archive = make_model_tar(tmp_path / "model.tar.gz")
    with archive.open("rb") as model_file:
        client.post(
            "/upload",
            data={"team_name": "Team", "racer_name": "Racer", "model_name": "Model", "notes": ""},
            files={"file": ("model.tar.gz", model_file, "application/gzip")},
        )
    submission_id = list_submissions(settings.db_path)[0]["id"]

    login = client.post("/admin/login", data={"password": "test-admin"}, follow_redirects=False)
    assert login.status_code == 303

    vehicle_response = client.post(
        "/admin/vehicles",
        data={"name": "Car 1", "console_url": "http://car.local", "console_password": "pw"},
        follow_redirects=False,
    )
    assert vehicle_response.status_code == 303

    approve_response = client.post(f"/admin/submissions/{submission_id}/approve", follow_redirects=False)
    assert approve_response.status_code == 303
    assert list_submissions(settings.db_path)[0]["status"] == "approved"

    vehicle_id = create_vehicle(settings.db_path, "Car 2", "http://car2.local", None)
    approve_submission(settings.db_path, submission_id)
    assert vehicle_id > 0
