from __future__ import annotations

from pathlib import Path

import pytest

from model_gateway.database import (
    SUBMISSION_APPROVED,
    VehicleBusyError,
    approve_submission,
    create_dispatch_if_available,
    create_submission,
    create_vehicle,
    get_dispatch,
    get_submission,
    init_db,
    update_dispatch_status,
    DISPATCH_FAILED,
    NewSubmission,
)


def _submission(path: Path) -> NewSubmission:
    return NewSubmission(
        team_name="Team",
        racer_name="Racer",
        model_name="Model",
        notes="",
        original_filename="model.tar.gz",
        storage_path=str(path),
        sha256="abc",
        size_bytes=123,
    )


def test_submission_approval_and_dispatch_lock(tmp_path: Path) -> None:
    db_path = tmp_path / "gateway.sqlite3"
    init_db(db_path)
    submission_id = create_submission(db_path, _submission(tmp_path / "model.tar.gz"))
    vehicle_id = create_vehicle(db_path, "Car 1", "http://car.local", None)

    approve_submission(db_path, submission_id)
    assert get_submission(db_path, submission_id)["status"] == SUBMISSION_APPROVED

    dispatch_id = create_dispatch_if_available(db_path, submission_id, vehicle_id)
    assert get_dispatch(db_path, dispatch_id)["status"] == "queued"

    second_submission_id = create_submission(db_path, _submission(tmp_path / "model2.tar.gz"))
    approve_submission(db_path, second_submission_id)
    with pytest.raises(VehicleBusyError):
        create_dispatch_if_available(db_path, second_submission_id, vehicle_id)

    update_dispatch_status(db_path, dispatch_id, DISPATCH_FAILED, "failed")
    second_dispatch_id = create_dispatch_if_available(db_path, second_submission_id, vehicle_id)
    assert second_dispatch_id != dispatch_id
