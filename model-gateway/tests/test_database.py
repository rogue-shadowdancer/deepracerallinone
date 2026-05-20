from __future__ import annotations

from pathlib import Path

import pytest

from model_gateway.database import (
    DISPATCH_FAILED,
    DISPATCH_QUEUED,
    ROLE_ADMIN,
    ROLE_USER,
    SUBMISSION_APPROVED,
    TEAM_MEMBER,
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
    get_team,
    get_dispatch,
    get_submission,
    get_user,
    get_vehicle,
    get_user_by_session,
    init_db,
    join_team,
    join_team_by_code,
    list_dispatch_attempts,
    move_user_to_team,
    regenerate_team_join_code,
    remove_team_member,
    start_dispatch_attempt,
    finish_dispatch_attempt,
    update_team_member_role,
    update_user,
    update_vehicle,
    update_dispatch_status,
    NewSubmission,
    create_event,
    create_round,
    get_active_round,
    list_audit_logs,
    list_events,
    list_rounds,
    record_audit_log,
    recover_interrupted_dispatches,
    schedule_dispatch_retry_or_fail,
    validate_round_upload,
)


def _seed_user_team(db_path: Path) -> tuple[int, int]:
    user_id = create_user(db_path, "racer", "Racer", "pw", role=ROLE_USER, status=USER_ACTIVE)
    team_id = create_team(db_path, "Team", max_members=2, leader_user_id=user_id)
    return user_id, team_id


def _submission(path: Path, user_id: int, team_id: int, *, round_id: int | None = None) -> NewSubmission:
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
        round_id=round_id,
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


def test_vehicle_update_preserves_replaces_and_clears_credentials(tmp_path: Path) -> None:
    db_path = tmp_path / "gateway.sqlite3"
    init_db(db_path)
    vehicle_id = create_vehicle(
        db_path,
        "Car",
        "http://car.local",
        "console",
        credential_secret="secret",
        ssh_password="ssh",
    )

    update_vehicle(
        db_path,
        vehicle_id,
        name="Car Updated",
        console_url="http://car2.local",
        credential_secret="secret",
        delivery_mode="ssh",
        ssh_host="car2.local",
        ssh_port=2222,
        ssh_username="deepracer",
        ssh_remote_artifact_root="/models",
    )
    vehicle = get_vehicle(db_path, vehicle_id)
    assert vehicle["name"] == "Car Updated"
    assert vehicle["delivery_mode"] == "ssh"
    assert vehicle["ssh_host"] == "car2.local"
    assert vehicle["has_console_password"]
    assert vehicle["has_ssh_password"]

    update_vehicle(
        db_path,
        vehicle_id,
        name="Car Updated",
        console_url="http://car2.local",
        credential_secret="secret",
        delivery_mode="ssh",
        clear_console_password=True,
        clear_ssh_password=True,
    )
    vehicle = get_vehicle(db_path, vehicle_id)
    assert not vehicle["has_console_password"]
    assert not vehicle["has_ssh_password"]


def test_update_user_edits_fields_team_and_protects_last_admin(tmp_path: Path) -> None:
    db_path = tmp_path / "gateway.sqlite3"
    init_db(db_path)
    admin_id = create_user(db_path, "admin", "Admin", "pw", role=ROLE_ADMIN, status=USER_ACTIVE)
    user_id = create_user(db_path, "racer", "Racer", "pw", role=ROLE_USER, status=USER_ACTIVE)
    team_id = create_team(db_path, "Team")

    update_user(
        db_path,
        user_id,
        username="pilot",
        display_name="Pilot",
        role=ROLE_USER,
        status=USER_ACTIVE,
        team_id=team_id,
        team_role=TEAM_LEADER,
    )
    user = get_user(db_path, user_id)
    assert user["username"] == "pilot"
    assert user["display_name"] == "Pilot"
    assert get_team(db_path, team_id)["members"][0]["role"] == TEAM_LEADER

    with pytest.raises(Exception, match="last active admin"):
        update_user(
            db_path,
            admin_id,
            username="admin",
            display_name="Admin",
            role=ROLE_USER,
            status=USER_ACTIVE,
        )


def test_team_join_code_and_member_editing(tmp_path: Path) -> None:
    db_path = tmp_path / "gateway.sqlite3"
    init_db(db_path)
    user_id = create_user(db_path, "racer", "Racer", "pw", role=ROLE_USER, status=USER_ACTIVE)
    team_id = create_team(db_path, "Team", max_members=1)
    old_code = get_team(db_path, team_id)["join_code"]
    new_code = regenerate_team_join_code(db_path, team_id)

    with pytest.raises(Exception, match="not found"):
        join_team_by_code(db_path, old_code, user_id)
    join_team_by_code(db_path, new_code, user_id)
    update_team_member_role(db_path, team_id, user_id, TEAM_LEADER)
    assert get_team(db_path, team_id)["members"][0]["role"] == TEAM_LEADER

    extra_id = create_user(db_path, "extra", "Extra", "pw", role=ROLE_USER, status=USER_ACTIVE)
    with pytest.raises(Exception, match="Team is full"):
        join_team(db_path, team_id, extra_id)

    remove_team_member(db_path, team_id, user_id)
    assert get_team(db_path, team_id)["member_count"] == 0


def test_schema_default_round_audit_and_round_limits(tmp_path: Path) -> None:
    db_path = tmp_path / "gateway.sqlite3"
    init_db(db_path)
    assert list_events(db_path)[0]["name"] == "Default Event"
    assert get_active_round(db_path)["name"] == "Practice Round"

    record_audit_log(db_path, actor_user_id=None, actor_username="system", actor_role="system", action="test.action")
    assert list_audit_logs(db_path)[0]["action"] == "test.action"

    user_id = create_user(db_path, "racer", "Racer", "pw", role=ROLE_USER, status=USER_ACTIVE)
    team_id = create_team(db_path, "Team", leader_user_id=user_id)
    event_id = create_event(db_path, "Race")
    round_id = create_round(db_path, event_id, "Limited", max_submissions_per_team=1)
    round_row = [row for row in list_rounds(db_path) if row["id"] == round_id][0]
    validate_round_upload(db_path, team_id, round_row)
    create_submission(db_path, _submission(tmp_path / "model.tar.gz", user_id, team_id, round_id=round_id))
    with pytest.raises(Exception, match="submission limit"):
        validate_round_upload(db_path, team_id, round_row)


def test_recover_and_schedule_dispatch_retry(tmp_path: Path) -> None:
    db_path = tmp_path / "gateway.sqlite3"
    init_db(db_path)
    user_id, team_id = _seed_user_team(db_path)
    submission_id = create_submission(db_path, _submission(tmp_path / "model.tar.gz", user_id, team_id))
    approve_submission(db_path, submission_id)
    vehicle_id = create_vehicle(db_path, "Car 1", "http://car.local", None)
    dispatch_id = create_dispatch_if_available(db_path, submission_id, vehicle_id)
    update_dispatch_status(db_path, dispatch_id, "uploading", "uploading")
    assert recover_interrupted_dispatches(db_path) == 1
    assert get_dispatch(db_path, dispatch_id)["status"] == DISPATCH_FAILED

    second_submission_id = create_submission(db_path, _submission(tmp_path / "model2.tar.gz", user_id, team_id))
    approve_submission(db_path, second_submission_id)
    second_dispatch_id = create_dispatch_if_available(db_path, second_submission_id, vehicle_id)
    assert schedule_dispatch_retry_or_fail(db_path, second_dispatch_id, second_submission_id, "network", max_retries=1, retry_delay_seconds=1)
    assert get_dispatch(db_path, second_dispatch_id)["status"] == DISPATCH_QUEUED
