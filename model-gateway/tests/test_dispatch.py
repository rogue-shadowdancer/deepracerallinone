from __future__ import annotations

from pathlib import Path

from model_gateway.config import Settings
from model_gateway.database import (
    DISPATCH_MODE_AUTO,
    DISPATCH_MODE_CONSOLE_API,
    DISPATCH_MODE_SSH,
    ROLE_USER,
    USER_ACTIVE,
    approve_submission,
    create_dispatch_if_available,
    create_submission,
    create_team,
    create_user,
    create_vehicle,
    get_dispatch,
    init_db,
    list_dispatch_attempts,
    NewSubmission,
)
from model_gateway.dispatch import dispatch_model_to_vehicle
from model_gateway.ssh_delivery import SshInstallResult
from model_gateway.vehicle import VehicleClientError

from conftest import make_model_tar


class FakeConsoleSuccess:
    calls: list[str] = []

    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def __enter__(self) -> "FakeConsoleSuccess":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        pass

    def login(self) -> None:
        self.calls.append("login")

    def upload_model(self, model_path: Path, upload_filename: str) -> str:
        self.calls.append(f"upload:{upload_filename}")
        return "uploaded"

    def wait_until_installed(self, folder_name: str) -> None:
        self.calls.append(f"wait:{folder_name}")


class FakeConsoleFailure(FakeConsoleSuccess):
    def upload_model(self, model_path: Path, upload_filename: str) -> str:
        raise VehicleClientError("console failed")


class FakeSshSuccess:
    calls: list[str] = []

    def __init__(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self.kwargs = kwargs

    def install_model(self, model_path: Path, upload_filename: str) -> SshInstallResult:
        self.calls.append(f"ssh:{upload_filename}")
        return SshInstallResult(folder_name=upload_filename[:-7], upload_message="ssh installed")


def _seed_dispatch(settings: Settings, tmp_path: Path, *, mode: str = DISPATCH_MODE_AUTO) -> int:
    init_db(settings.db_path)
    archive = make_model_tar(tmp_path / "model.tar.gz")
    user_id = create_user(settings.db_path, "racer", "Racer", "pw", role=ROLE_USER, status=USER_ACTIVE)
    team_id = create_team(settings.db_path, "Team", leader_user_id=user_id)
    submission_id = create_submission(
        settings.db_path,
        NewSubmission(
            user_id=user_id,
            team_id=team_id,
            username_snapshot="racer",
            display_name_snapshot="Racer",
            team_name_snapshot="Team",
            team_members_snapshot="[]",
            model_name="Model",
            notes="",
            original_filename="model.tar.gz",
            storage_path=str(archive),
            sha256="abc",
            size_bytes=123,
        ),
    )
    approve_submission(settings.db_path, submission_id)
    vehicle_id = create_vehicle(
        settings.db_path,
        "Car",
        "http://car.local",
        "console-pw",
        credential_secret=settings.credential_secret,
        delivery_mode=DISPATCH_MODE_AUTO,
        ssh_host="car.local",
        ssh_username="deepracer",
        ssh_password="ssh-pw",
    )
    return create_dispatch_if_available(settings.db_path, submission_id, vehicle_id, requested_mode=mode)


def test_auto_dispatch_uses_console_without_ssh(settings: Settings, tmp_path: Path) -> None:
    FakeConsoleSuccess.calls = []
    FakeSshSuccess.calls = []
    dispatch_id = _seed_dispatch(settings, tmp_path)

    dispatch_model_to_vehicle(settings, dispatch_id, client_factory=FakeConsoleSuccess, ssh_client_factory=FakeSshSuccess)

    assert get_dispatch(settings.db_path, dispatch_id)["status"] == "installed"
    assert FakeConsoleSuccess.calls == ["login", "upload:model.tar.gz", "wait:model"]
    assert FakeSshSuccess.calls == []
    assert [attempt["mode"] for attempt in list_dispatch_attempts(settings.db_path, dispatch_id)] == [DISPATCH_MODE_CONSOLE_API]


def test_auto_dispatch_falls_back_to_ssh(settings: Settings, tmp_path: Path) -> None:
    FakeSshSuccess.calls = []
    dispatch_id = _seed_dispatch(settings, tmp_path)

    dispatch_model_to_vehicle(settings, dispatch_id, client_factory=FakeConsoleFailure, ssh_client_factory=FakeSshSuccess)

    assert get_dispatch(settings.db_path, dispatch_id)["status"] == "installed"
    assert FakeSshSuccess.calls == ["ssh:model.tar.gz"]
    assert [attempt["mode"] for attempt in list_dispatch_attempts(settings.db_path, dispatch_id)] == [
        DISPATCH_MODE_CONSOLE_API,
        DISPATCH_MODE_SSH,
    ]


def test_manual_ssh_dispatch_skips_console(settings: Settings, tmp_path: Path) -> None:
    FakeConsoleSuccess.calls = []
    FakeSshSuccess.calls = []
    dispatch_id = _seed_dispatch(settings, tmp_path, mode=DISPATCH_MODE_SSH)

    dispatch_model_to_vehicle(settings, dispatch_id, client_factory=FakeConsoleSuccess, ssh_client_factory=FakeSshSuccess)

    assert get_dispatch(settings.db_path, dispatch_id)["status"] == "installed"
    assert FakeConsoleSuccess.calls == []
    assert FakeSshSuccess.calls == ["ssh:model.tar.gz"]
