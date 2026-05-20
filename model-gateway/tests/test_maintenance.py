from __future__ import annotations

import tarfile
from pathlib import Path

import pytest

from model_gateway.config import Settings
from model_gateway.database import (
    ROLE_USER,
    SUBMISSION_FAILED,
    NewSubmission,
    create_submission,
    create_team,
    create_user,
    init_db,
    update_submission_status,
)
from model_gateway.maintenance import backup, cleanup_preview, restore


def test_backup_restore_and_cleanup_preview(settings: Settings, tmp_path: Path) -> None:
    init_db(settings.db_path)
    archive_dir = tmp_path / "archives"
    archive = backup(settings, archive_dir)
    assert archive.is_file()

    restored = Settings(data_dir=tmp_path / "restored", session_secret="x", credential_secret="y")
    restore(restored, archive)
    assert restored.db_path.is_file()

    user_id = create_user(settings.db_path, "racer", "Racer", "pw", role=ROLE_USER, status="active")
    team_id = create_team(settings.db_path, "Team", leader_user_id=user_id)
    upload_dir = settings.upload_dir / "deadbeef"
    upload_dir.mkdir(parents=True)
    model_path = upload_dir / "model.tar.gz"
    model_path.write_bytes(b"model")
    submission_id = create_submission(
        settings.db_path,
        NewSubmission(
            user_id=user_id,
            team_id=team_id,
            username_snapshot="racer",
            display_name_snapshot="Racer",
            team_name_snapshot="Team",
            team_members_snapshot="[]",
            model_name="Failed",
            notes="",
            original_filename="model.tar.gz",
            storage_path=str(model_path),
            sha256="abc",
            size_bytes=model_path.stat().st_size,
        ),
    )
    update_submission_status(settings.db_path, submission_id, SUBMISSION_FAILED, "failed")
    preview = cleanup_preview(settings, 0)
    assert preview["count"] == 1
    assert preview["total_bytes"] >= model_path.stat().st_size


def test_restore_rejects_unsafe_or_incomplete_archive(settings: Settings, tmp_path: Path) -> None:
    unsafe_archive = tmp_path / "unsafe.tar.gz"
    with tarfile.open(unsafe_archive, "w:gz") as archive:
        info = tarfile.TarInfo("../gateway.sqlite3")
        info.size = 0
        archive.addfile(info)

    with pytest.raises(ValueError, match="gateway.sqlite3|Unsafe"):
        restore(settings, unsafe_archive)
