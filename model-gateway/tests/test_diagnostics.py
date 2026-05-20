from __future__ import annotations

from model_gateway.config import Settings
from model_gateway.database import create_vehicle, init_db, list_latest_vehicle_health
from model_gateway.diagnostics import run_vehicle_diagnostics


class FakeConsole:
    def __init__(self, *_args, **_kwargs) -> None:
        self._csrf_token = "token"

    def login(self) -> None:
        pass

    def model_loading_status(self) -> str:
        return "ready"

    def is_model_installed(self, _folder_name: str) -> bool:
        return False

    def close(self) -> None:
        pass


class FakeSsh:
    def __init__(self, **_kwargs) -> None:  # type: ignore[no-untyped-def]
        pass

    def diagnostics(self) -> dict[str, object]:
        return {
            "steps": [
                {"name": "ssh_connect", "status": "ready", "message": "ok", "duration_seconds": 0, "output": "", "suggestion": ""},
                {"name": "model_loader_service", "status": "ready", "message": "ok", "duration_seconds": 0, "output": "", "suggestion": ""},
            ],
            "snapshot": {"rsync_available": True, "disk_free_bytes": 123456, "remote_artifact_root": "/tmp"},
        }


class FakeBadSsh:
    def __init__(self, **_kwargs) -> None:  # type: ignore[no-untyped-def]
        pass

    def diagnostics(self) -> dict[str, object]:
        return {
            "steps": [
                {
                    "name": "ssh_connect",
                    "status": "error",
                    "message": "host key fingerprint does not match",
                    "duration_seconds": 0,
                    "output": "",
                    "suggestion": "check fingerprint",
                }
            ],
            "snapshot": {"rsync_available": False, "disk_free_bytes": None},
        }


def test_vehicle_diagnostics_success(settings: Settings) -> None:
    init_db(settings.db_path)
    vehicle_id = create_vehicle(
        settings.db_path,
        "Car",
        "http://car.local",
        None,
        ssh_host="car.local",
        ssh_username="deepracer",
    )

    result = run_vehicle_diagnostics(settings, vehicle_id, client_factory=FakeConsole, ssh_client_factory=FakeSsh)

    assert result["overall_status"] == "ready"
    assert result["snapshot"]["console_csrf_token_present"] is True
    assert list_latest_vehicle_health(settings.db_path)[vehicle_id]["disk_free_bytes"] == 123456


def test_vehicle_diagnostics_records_ssh_failure(settings: Settings) -> None:
    init_db(settings.db_path)
    vehicle_id = create_vehicle(
        settings.db_path,
        "Car",
        "",
        None,
        ssh_host="car.local",
        ssh_username="deepracer",
    )

    result = run_vehicle_diagnostics(settings, vehicle_id, ssh_client_factory=FakeBadSsh)

    assert result["overall_status"] == "error"
    assert "failed" in list_latest_vehicle_health(settings.db_path)[vehicle_id]["ssh_status"]
