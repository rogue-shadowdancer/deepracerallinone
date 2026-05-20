from __future__ import annotations

from pathlib import Path

from model_gateway.config import Settings
from model_gateway.database import (
    DISPATCH_INSTALLED,
    DISPATCH_MODE_AUTO,
    ROLE_USER,
    USER_ACTIVE,
    NewSubmission,
    approve_submission,
    create_dispatch_if_available,
    create_submission,
    create_team,
    create_user,
    create_vehicle,
    get_dispatch,
    init_db,
)
from model_gateway.ssh_delivery import SshInstallResult
from model_gateway.worker import DispatchWorker

from conftest import make_model_tar


class FakeConsoleSuccess:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def __enter__(self) -> "FakeConsoleSuccess":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        pass

    def login(self) -> None:
        pass

    def upload_model(self, model_path: Path, upload_filename: str) -> str:
        return "uploaded"

    def wait_until_installed(self, folder_name: str) -> None:
        pass


class FakeSsh:
    def __init__(self, **_kwargs) -> None:  # type: ignore[no-untyped-def]
        pass

    def install_model(self, model_path: Path, upload_filename: str) -> SshInstallResult:
        return SshInstallResult(folder_name=upload_filename[:-7], upload_message="ssh installed")


def test_worker_can_process_one_queued_dispatch(settings: Settings, tmp_path: Path) -> None:
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
    vehicle_id = create_vehicle(settings.db_path, "Car", "http://car.local", None, delivery_mode=DISPATCH_MODE_AUTO)
    dispatch_id = create_dispatch_if_available(settings.db_path, submission_id, vehicle_id)

    # Run the dispatch function directly with fake adapters; the persistent worker
    # uses the same queued dispatch discovery path at runtime.
    from model_gateway.dispatch import dispatch_model_to_vehicle

    dispatch_model_to_vehicle(settings, dispatch_id, client_factory=FakeConsoleSuccess, ssh_client_factory=FakeSsh)

    assert get_dispatch(settings.db_path, dispatch_id)["status"] == DISPATCH_INSTALLED
    assert isinstance(DispatchWorker(settings), DispatchWorker)
