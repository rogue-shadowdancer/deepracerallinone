from __future__ import annotations

from pathlib import Path

import pytest

from model_gateway.database import (
    DISPATCH_FAILED,
    ROLE_USER,
    SUBMISSION_APPROVED,
    TEAM_LEADER,
    USER_ACTIVE,
    USER_PENDING,
    VehicleBusyError,
    approve_submission,
    approve_user,
    authenticate_user,
    create_dispatch_if_available,
    create_session,
    create_submission,
    create_team,
    create_user,
    create_vehicle,
    cancel_dispatch,
    get_dispatch,
    get_submission,
    get_user_by_session,
    init_db,
    join_team,
    list_dispatch_attempts,
    move_user_to_team,
    start_dispatch_attempt,
    finish_dispatch_attempt,
    update_dispatch_status,
    NewSubmission,
)


def _seed_user_team(db_path: Path) -> tuple[int, int]:
    user_id = create_user(db_path, "racer", "Racer", "pw", role=ROLE_USER, status=USER_ACTIVE)
    team_id = create_team(db_path, "Team", max_members=2, leader_user_id=user_id)
    return user_id, team_id


def _submission(path: Path, user_id: int, team_id: int) -> NewSubmission:
    return NewSubmission(
        user_id=user_id,
        team_id=team_id,
        username_snapshot="racer",
        display_name_snapshot="Racer",
        team_name_snapshot="Team",
        team_members_snapshot="[]",
        model_name="Model",
        notes="",
        original_filename="model.tar.gz",
        storage_path=str(path),
        sha256="abc",
        size_bytes=123,
    )


def test_session_multi_login_and_pending_user_gate(tmp_path: Path) -> None:
    db_path = tmp_path / "gateway.sqlite3"
    init_db(db_path)
    pending_id = create_user(db_path, "pending", "Pending", "pw", role=ROLE_USER, status=USER_PENDING)

    assert authenticate_user(db_path, "pending", "pw", role=ROLE_USER) is None
    approve_user(db_path, pending_id)
    user = authenticate_user(db_path, "pending", "pw", role=ROLE_USER)
    assert user is not None

    token_1 = create_session(db_path, pending_id, "one")
    token_2 = create_session(db_path, pending_id, "two")
    assert get_user_by_session(db_path, token_1, role=ROLE_USER)["username"] == "pending"
    assert get_user_by_session(db_path, token_2, role=ROLE_USER)["username"] == "pending"


def test_team_limit_and_member_move(tmp_path: Path) -> None:
    db_path = tmp_path / "gateway.sqlite3"
    init_db(db_path)
    leader_id, team_id = _seed_user_team(db_path)
    member_id = create_user(db_path, "member", "Member", "pw", role=ROLE_USER, status=USER_ACTIVE)
    extra_id = create_user(db_path, "extra", "Extra", "pw", role=ROLE_USER, status=USER_ACTIVE)

    join_team(db_path, team_id, member_id)
    with pytest.raises(Exception, match="Team is full"):
        join_team(db_path, team_id, extra_id)

    other_team_id = create_team(db_path, "Other", max_members=2)
    move_user_to_team(db_path, leader_id, other_team_id, role=TEAM_LEADER)


def test_submission_approval_and_dispatch_lock(tmp_path: Path) -> None:
    db_path = tmp_path / "gateway.sqlite3"
    init_db(db_path)
    user_id, team_id = _seed_user_team(db_path)
    submission_id = create_submission(db_path, _submission(tmp_path / "model.tar.gz", user_id, team_id))
    vehicle_id = create_vehicle(db_path, "Car 1", "http://car.local", None)

    approve_submission(db_path, submission_id)
    assert get_submission(db_path, submission_id)["status"] == SUBMISSION_APPROVED

    dispatch_id = create_dispatch_if_available(db_path, submission_id, vehicle_id)
    assert get_dispatch(db_path, dispatch_id)["status"] == "queued"

    second_submission_id = create_submission(db_path, _submission(tmp_path / "model2.tar.gz", user_id, team_id))
    approve_submission(db_path, second_submission_id)
    with pytest.raises(VehicleBusyError):
        create_dispatch_if_available(db_path, second_submission_id, vehicle_id)

    update_dispatch_status(db_path, dispatch_id, DISPATCH_FAILED, "failed")
    second_dispatch_id = create_dispatch_if_available(db_path, second_submission_id, vehicle_id)
    assert second_dispatch_id != dispatch_id


def test_dispatch_attempts_are_recorded(tmp_path: Path) -> None:
    db_path = tmp_path / "gateway.sqlite3"
    init_db(db_path)
    user_id, team_id = _seed_user_team(db_path)
    submission_id = create_submission(db_path, _submission(tmp_path / "model.tar.gz", user_id, team_id))
    approve_submission(db_path, submission_id)
    vehicle_id = create_vehicle(db_path, "Car 1", "http://car.local", None)
    dispatch_id = create_dispatch_if_available(db_path, submission_id, vehicle_id)

    attempt_id = start_dispatch_attempt(db_path, dispatch_id, "console_api", "starting")
    finish_dispatch_attempt(db_path, attempt_id, "failed", "no route")

    attempts = list_dispatch_attempts(db_path, dispatch_id)
    assert attempts[0]["mode"] == "console_api"
    assert attempts[0]["status"] == "failed"


def test_cancel_queued_dispatch_returns_submission_to_approved(tmp_path: Path) -> None:
    db_path = tmp_path / "gateway.sqlite3"
    init_db(db_path)
    user_id, team_id = _seed_user_team(db_path)
    submission_id = create_submission(db_path, _submission(tmp_path / "model.tar.gz", user_id, team_id))
    approve_submission(db_path, submission_id)
    vehicle_id = create_vehicle(db_path, "Car 1", "http://car.local", None)
    dispatch_id = create_dispatch_if_available(db_path, submission_id, vehicle_id)

    cancel_dispatch(db_path, dispatch_id)

    assert get_dispatch(db_path, dispatch_id)["status"] == "cancelled"
    assert get_submission(db_path, submission_id)["status"] == SUBMISSION_APPROVED
