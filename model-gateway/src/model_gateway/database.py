from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from model_gateway.security import (
    CredentialCodec,
    generate_join_code,
    generate_password,
    hash_password,
    hash_session_token,
    new_session_token,
    verify_password,
)


ROLE_ADMIN = "admin"
ROLE_USER = "user"

USER_ACTIVE = "active"
USER_PENDING = "pending"
USER_DISABLED = "disabled"

TEAM_ACTIVE = "active"
TEAM_DISABLED = "disabled"
TEAM_MEMBER = "member"
TEAM_LEADER = "leader"

SETTING_REGISTRATION_ENABLED = "registration_enabled"
SETTING_DEFAULT_TEAM_MAX_MEMBERS = "default_team_max_members"

SUBMISSION_UPLOADED = "uploaded"
SUBMISSION_APPROVED = "approved"
SUBMISSION_REJECTED = "rejected"
SUBMISSION_DISPATCHING = "dispatching"
SUBMISSION_INSTALLED = "installed"
SUBMISSION_FAILED = "failed"

DISPATCH_QUEUED = "queued"
DISPATCH_UPLOADING = "uploading"
DISPATCH_VERIFYING = "verifying"
DISPATCH_INSTALLING = "installing"
DISPATCH_INSTALLED = "installed"
DISPATCH_FAILED = "failed"
DISPATCH_CANCELLED = "cancelled"

ACTIVE_DISPATCH_STATUSES = (DISPATCH_QUEUED, DISPATCH_UPLOADING, DISPATCH_VERIFYING, DISPATCH_INSTALLING)
DISPATCH_MODE_AUTO = "auto"
DISPATCH_MODE_CONSOLE_API = "console_api"
DISPATCH_MODE_SSH = "ssh"
DISPATCH_MODES = {DISPATCH_MODE_AUTO, DISPATCH_MODE_CONSOLE_API, DISPATCH_MODE_SSH}
_UNSET = object()


class GatewayStateError(ValueError):
    """Raised when a requested state transition is invalid."""


class VehicleBusyError(GatewayStateError):
    """Raised when a vehicle already has an active dispatch."""


class AuthError(ValueError):
    """Raised when authentication or authorization fails."""


@dataclass(frozen=True)
class NewSubmission:
    user_id: int
    team_id: int
    username_snapshot: str
    display_name_snapshot: str
    team_name_snapshot: str
    team_members_snapshot: str
    model_name: str
    notes: str
    original_filename: str
    storage_path: str
    sha256: str
    size_bytes: int
    warning: str | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return None if row is None else dict(row)


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(db_path)) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_login_at TEXT
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_hash TEXT NOT NULL UNIQUE,
                user_agent TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                revoked_at TEXT
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                join_code TEXT NOT NULL UNIQUE,
                max_members INTEGER,
                status TEXT NOT NULL,
                created_by_user_id INTEGER REFERENCES users(id),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS team_memberships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(user_id)
            );

            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                team_id INTEGER REFERENCES teams(id),
                username_snapshot TEXT,
                display_name_snapshot TEXT,
                team_name_snapshot TEXT,
                team_members_snapshot TEXT,
                model_name TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                original_filename TEXT NOT NULL,
                storage_path TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                status TEXT NOT NULL,
                warning TEXT,
                reject_reason TEXT,
                failure_reason TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS vehicles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                console_url TEXT NOT NULL DEFAULT '',
                console_password_encrypted TEXT,
                delivery_mode TEXT NOT NULL DEFAULT 'auto',
                ssh_host TEXT NOT NULL DEFAULT '',
                ssh_port INTEGER NOT NULL DEFAULT 22,
                ssh_username TEXT NOT NULL DEFAULT '',
                ssh_password_encrypted TEXT,
                ssh_private_key_path TEXT NOT NULL DEFAULT '',
                ssh_remote_artifact_root TEXT NOT NULL DEFAULT '/opt/aws/deepracer/artifacts',
                ssh_install_command_template TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS dispatches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                submission_id INTEGER NOT NULL REFERENCES submissions(id),
                vehicle_id INTEGER NOT NULL REFERENCES vehicles(id),
                requested_mode TEXT NOT NULL DEFAULT 'auto',
                status TEXT NOT NULL,
                message TEXT NOT NULL DEFAULT '',
                cancel_requested INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT
            );

            CREATE TABLE IF NOT EXISTS dispatch_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dispatch_id INTEGER NOT NULL REFERENCES dispatches(id) ON DELETE CASCADE,
                mode TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT NOT NULL DEFAULT '',
                started_at TEXT NOT NULL,
                finished_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON sessions(token_hash);
            CREATE INDEX IF NOT EXISTS idx_submissions_status ON submissions(status);
            CREATE INDEX IF NOT EXISTS idx_dispatches_vehicle_status ON dispatches(vehicle_id, status);
            CREATE INDEX IF NOT EXISTS idx_dispatch_attempts_dispatch_id ON dispatch_attempts(dispatch_id);
            """
        )
        _migrate_existing_tables(connection)
        _ensure_setting(connection, SETTING_REGISTRATION_ENABLED, "false")
        _ensure_setting(connection, SETTING_DEFAULT_TEAM_MAX_MEMBERS, "")
        connection.commit()


def _migrate_existing_tables(connection: sqlite3.Connection) -> None:
    _ensure_columns(
        connection,
        "submissions",
        {
            "user_id": "INTEGER REFERENCES users(id)",
            "team_id": "INTEGER REFERENCES teams(id)",
            "username_snapshot": "TEXT",
            "display_name_snapshot": "TEXT",
            "team_name_snapshot": "TEXT",
            "team_members_snapshot": "TEXT",
        },
    )
    _ensure_columns(
        connection,
        "vehicles",
        {
            "console_password_encrypted": "TEXT",
            "delivery_mode": "TEXT NOT NULL DEFAULT 'auto'",
            "ssh_host": "TEXT NOT NULL DEFAULT ''",
            "ssh_port": "INTEGER NOT NULL DEFAULT 22",
            "ssh_username": "TEXT NOT NULL DEFAULT ''",
            "ssh_password_encrypted": "TEXT",
            "ssh_private_key_path": "TEXT NOT NULL DEFAULT ''",
            "ssh_remote_artifact_root": "TEXT NOT NULL DEFAULT '/opt/aws/deepracer/artifacts'",
            "ssh_install_command_template": "TEXT NOT NULL DEFAULT ''",
            "notes": "TEXT NOT NULL DEFAULT ''",
        },
    )
    _ensure_columns(
        connection,
        "dispatches",
        {
            "requested_mode": "TEXT NOT NULL DEFAULT 'auto'",
            "cancel_requested": "INTEGER NOT NULL DEFAULT 0",
        },
    )


def _ensure_columns(connection: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
    for column, definition in columns.items():
        if column not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _ensure_setting(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))


def ensure_bootstrap_admin(db_path: Path, username: str, password: str) -> int:
    with closing(connect(db_path)) as connection:
        row = connection.execute("SELECT id FROM users WHERE role = ? LIMIT 1", (ROLE_ADMIN,)).fetchone()
        if row is not None:
            return int(row["id"])
    return create_user(db_path, username, username, password, role=ROLE_ADMIN, status=USER_ACTIVE)


def create_user(
    db_path: Path,
    username: str,
    display_name: str,
    password: str,
    *,
    role: str = ROLE_USER,
    status: str = USER_ACTIVE,
) -> int:
    if role not in {ROLE_ADMIN, ROLE_USER}:
        raise GatewayStateError("Invalid user role")
    if status not in {USER_ACTIVE, USER_PENDING, USER_DISABLED}:
        raise GatewayStateError("Invalid user status")
    username = normalize_username(username)
    display_name = display_name.strip() or username
    now = utc_now()
    with closing(connect(db_path)) as connection:
        cursor = connection.execute(
            """
            INSERT INTO users (username, display_name, role, password_hash, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (username, display_name, role, hash_password(password), status, now, now),
        )
        connection.commit()
        return int(cursor.lastrowid)


def normalize_username(username: str) -> str:
    value = username.strip().lower()
    if not value:
        raise GatewayStateError("Username is required")
    return value


def list_users(db_path: Path) -> list[dict[str, Any]]:
    with closing(connect(db_path)) as connection:
        rows = connection.execute(
            """
            SELECT
                u.*,
                t.name AS team_name,
                COUNT(s.id) FILTER (WHERE s.revoked_at IS NULL) AS active_sessions
            FROM users u
            LEFT JOIN team_memberships tm ON tm.user_id = u.id
            LEFT JOIN teams t ON t.id = tm.team_id
            LEFT JOIN sessions s ON s.user_id = u.id
            GROUP BY u.id
            ORDER BY u.role, u.username
            """
        ).fetchall()
        return [dict(row) for row in rows]


def get_user(db_path: Path, user_id: int) -> dict[str, Any] | None:
    with closing(connect(db_path)) as connection:
        return row_to_dict(connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())


def get_user_by_username(db_path: Path, username: str) -> dict[str, Any] | None:
    with closing(connect(db_path)) as connection:
        return row_to_dict(connection.execute("SELECT * FROM users WHERE username = ?", (normalize_username(username),)).fetchone())


def authenticate_user(db_path: Path, username: str, password: str, *, role: str | None = None) -> dict[str, Any] | None:
    user = get_user_by_username(db_path, username)
    if user is None:
        return None
    if role is not None and user["role"] != role:
        return None
    if user["status"] != USER_ACTIVE:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    with closing(connect(db_path)) as connection:
        connection.execute(
            "UPDATE users SET last_login_at = ?, updated_at = ? WHERE id = ?",
            (utc_now(), utc_now(), int(user["id"])),
        )
        connection.commit()
    user["last_login_at"] = utc_now()
    return user


def create_session(db_path: Path, user_id: int, user_agent: str = "") -> str:
    token = new_session_token()
    now = utc_now()
    with closing(connect(db_path)) as connection:
        connection.execute(
            """
            INSERT INTO sessions (user_id, token_hash, user_agent, created_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, hash_session_token(token), user_agent[:300], now, now),
        )
        connection.commit()
    return token


def get_user_by_session(db_path: Path, token: str | None, *, role: str | None = None) -> dict[str, Any] | None:
    if not token:
        return None
    token_hash = hash_session_token(token)
    with closing(connect(db_path)) as connection:
        row = connection.execute(
            """
            SELECT u.*, s.id AS session_id
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = ? AND s.revoked_at IS NULL
            """,
            (token_hash,),
        ).fetchone()
        if row is None:
            return None
        user = dict(row)
        if user["status"] != USER_ACTIVE:
            return None
        if role is not None and user["role"] != role:
            return None
        connection.execute("UPDATE sessions SET last_seen_at = ? WHERE id = ?", (utc_now(), int(user["session_id"])))
        connection.commit()
        return user


def revoke_session(db_path: Path, token: str) -> None:
    with closing(connect(db_path)) as connection:
        connection.execute(
            "UPDATE sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
            (utc_now(), hash_session_token(token)),
        )
        connection.commit()


def revoke_session_by_id(db_path: Path, session_id: int) -> None:
    with closing(connect(db_path)) as connection:
        connection.execute(
            "UPDATE sessions SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
            (utc_now(), session_id),
        )
        connection.commit()


def list_sessions(db_path: Path) -> list[dict[str, Any]]:
    with closing(connect(db_path)) as connection:
        rows = connection.execute(
            """
            SELECT s.*, u.username, u.display_name, u.role
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            ORDER BY s.last_seen_at DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]


def approve_user(db_path: Path, user_id: int) -> None:
    set_user_status(db_path, user_id, USER_ACTIVE)


def disable_user(db_path: Path, user_id: int) -> None:
    set_user_status(db_path, user_id, USER_DISABLED)
    with closing(connect(db_path)) as connection:
        connection.execute(
            "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
            (utc_now(), user_id),
        )
        connection.commit()


def set_user_status(db_path: Path, user_id: int, status: str) -> None:
    if status not in {USER_ACTIVE, USER_PENDING, USER_DISABLED}:
        raise GatewayStateError("Invalid user status")
    with closing(connect(db_path)) as connection:
        cursor = connection.execute(
            "UPDATE users SET status = ?, updated_at = ? WHERE id = ?",
            (status, utc_now(), user_id),
        )
        if cursor.rowcount == 0:
            raise GatewayStateError("User not found")
        connection.commit()


def reset_user_password(db_path: Path, user_id: int, password: str | None = None) -> str:
    password = password or generate_password()
    with closing(connect(db_path)) as connection:
        cursor = connection.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
            (hash_password(password), utc_now(), user_id),
        )
        if cursor.rowcount == 0:
            raise GatewayStateError("User not found")
        connection.commit()
    return password


def get_setting(db_path: Path, key: str, default: str = "") -> str:
    with closing(connect(db_path)) as connection:
        row = connection.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return default if row is None else str(row["value"])


def set_setting(db_path: Path, key: str, value: str) -> None:
    with closing(connect(db_path)) as connection:
        connection.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        connection.commit()


def is_registration_enabled(db_path: Path) -> bool:
    return get_setting(db_path, SETTING_REGISTRATION_ENABLED, "false").lower() == "true"


def default_team_max_members(db_path: Path) -> int | None:
    raw = get_setting(db_path, SETTING_DEFAULT_TEAM_MAX_MEMBERS, "")
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def create_team(
    db_path: Path,
    name: str,
    *,
    created_by_user_id: int | None = None,
    max_members: int | None = None,
    leader_user_id: int | None = None,
) -> int:
    name = name.strip()
    if not name:
        raise GatewayStateError("Team name is required")
    now = utc_now()
    join_code = _unique_join_code(db_path)
    if max_members is not None and max_members <= 0:
        max_members = None
    with closing(connect(db_path)) as connection:
        cursor = connection.execute(
            """
            INSERT INTO teams (name, join_code, max_members, status, created_by_user_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (name, join_code, max_members, TEAM_ACTIVE, created_by_user_id, now, now),
        )
        team_id = int(cursor.lastrowid)
        if leader_user_id is not None:
            _join_team_with_connection(connection, team_id, leader_user_id, TEAM_LEADER)
        connection.commit()
        return team_id


def _unique_join_code(db_path: Path) -> str:
    with closing(connect(db_path)) as connection:
        while True:
            code = generate_join_code()
            row = connection.execute("SELECT id FROM teams WHERE join_code = ?", (code,)).fetchone()
            if row is None:
                return code


def list_teams(db_path: Path) -> list[dict[str, Any]]:
    with closing(connect(db_path)) as connection:
        rows = connection.execute(
            """
            SELECT
                t.*,
                COUNT(tm.id) AS member_count
            FROM teams t
            LEFT JOIN team_memberships tm ON tm.team_id = t.id
            GROUP BY t.id
            ORDER BY t.name
            """
        ).fetchall()
        teams = [dict(row) for row in rows]
        for team in teams:
            team["members"] = list_team_members(db_path, int(team["id"]))
        return teams


def get_team(db_path: Path, team_id: int) -> dict[str, Any] | None:
    with closing(connect(db_path)) as connection:
        team = row_to_dict(connection.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone())
    if team is not None:
        team["members"] = list_team_members(db_path, team_id)
        team["member_count"] = len(team["members"])
    return team


def get_team_by_join_code(db_path: Path, join_code: str) -> dict[str, Any] | None:
    with closing(connect(db_path)) as connection:
        team = row_to_dict(
            connection.execute("SELECT * FROM teams WHERE join_code = ?", (join_code.strip().upper(),)).fetchone()
        )
    if team is not None:
        team["members"] = list_team_members(db_path, int(team["id"]))
        team["member_count"] = len(team["members"])
    return team


def get_team_by_name(db_path: Path, name: str) -> dict[str, Any] | None:
    with closing(connect(db_path)) as connection:
        team = row_to_dict(connection.execute("SELECT * FROM teams WHERE name = ?", (name.strip(),)).fetchone())
    if team is not None:
        team["members"] = list_team_members(db_path, int(team["id"]))
        team["member_count"] = len(team["members"])
    return team


def list_team_members(db_path: Path, team_id: int) -> list[dict[str, Any]]:
    with closing(connect(db_path)) as connection:
        rows = connection.execute(
            """
            SELECT tm.*, u.username, u.display_name, u.status
            FROM team_memberships tm
            JOIN users u ON u.id = tm.user_id
            WHERE tm.team_id = ?
            ORDER BY tm.role DESC, u.display_name
            """,
            (team_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_user_team(db_path: Path, user_id: int) -> dict[str, Any] | None:
    with closing(connect(db_path)) as connection:
        row = connection.execute(
            """
            SELECT t.*, tm.role AS membership_role
            FROM team_memberships tm
            JOIN teams t ON t.id = tm.team_id
            WHERE tm.user_id = ? AND t.status = ?
            """,
            (user_id, TEAM_ACTIVE),
        ).fetchone()
    if row is None:
        return None
    team = dict(row)
    team["members"] = list_team_members(db_path, int(team["id"]))
    team["member_count"] = len(team["members"])
    return team


def join_team(db_path: Path, team_id: int, user_id: int, *, role: str = TEAM_MEMBER) -> None:
    with closing(connect(db_path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _join_team_with_connection(connection, team_id, user_id, role)
        connection.commit()


def _join_team_with_connection(connection: sqlite3.Connection, team_id: int, user_id: int, role: str) -> None:
    if role not in {TEAM_MEMBER, TEAM_LEADER}:
        raise GatewayStateError("Invalid team role")
    team = connection.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
    if team is None or team["status"] != TEAM_ACTIVE:
        raise GatewayStateError("Team is not active")
    existing = connection.execute("SELECT id FROM team_memberships WHERE user_id = ?", (user_id,)).fetchone()
    if existing is not None:
        raise GatewayStateError("User already belongs to a team")
    member_count = int(connection.execute("SELECT COUNT(*) AS count FROM team_memberships WHERE team_id = ?", (team_id,)).fetchone()["count"])
    if team["max_members"] is not None and member_count >= int(team["max_members"]):
        raise GatewayStateError("Team is full")
    connection.execute(
        "INSERT INTO team_memberships (team_id, user_id, role, created_at) VALUES (?, ?, ?, ?)",
        (team_id, user_id, role, utc_now()),
    )


def join_team_by_code(db_path: Path, join_code: str, user_id: int) -> None:
    team = get_team_by_join_code(db_path, join_code)
    if team is None:
        raise GatewayStateError("Team join code not found")
    join_team(db_path, int(team["id"]), user_id)


def leave_team(db_path: Path, user_id: int) -> None:
    with closing(connect(db_path)) as connection:
        connection.execute("DELETE FROM team_memberships WHERE user_id = ?", (user_id,))
        connection.commit()


def update_team(
    db_path: Path,
    team_id: int,
    *,
    name: str | None = None,
    max_members: int | None = None,
    status: str | None = None,
) -> None:
    team = get_team(db_path, team_id)
    if team is None:
        raise GatewayStateError("Team not found")
    new_name = name.strip() if name is not None and name.strip() else team["name"]
    new_status = status or team["status"]
    if new_status not in {TEAM_ACTIVE, TEAM_DISABLED}:
        raise GatewayStateError("Invalid team status")
    if max_members is not None and max_members <= 0:
        max_members = None
    with closing(connect(db_path)) as connection:
        connection.execute(
            "UPDATE teams SET name = ?, max_members = ?, status = ?, updated_at = ? WHERE id = ?",
            (new_name, max_members, new_status, utc_now(), team_id),
        )
        connection.commit()


def move_user_to_team(db_path: Path, user_id: int, team_id: int, *, role: str = TEAM_MEMBER) -> None:
    with closing(connect(db_path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DELETE FROM team_memberships WHERE user_id = ?", (user_id,))
        _join_team_with_connection(connection, team_id, user_id, role)
        connection.commit()


def create_submission(db_path: Path, submission: NewSubmission) -> int:
    now = utc_now()
    values: dict[str, Any] = {
        "user_id": submission.user_id,
        "team_id": submission.team_id,
        "username_snapshot": submission.username_snapshot,
        "display_name_snapshot": submission.display_name_snapshot,
        "team_name_snapshot": submission.team_name_snapshot,
        "team_members_snapshot": submission.team_members_snapshot,
        "model_name": submission.model_name,
        "notes": submission.notes,
        "original_filename": submission.original_filename,
        "storage_path": submission.storage_path,
        "sha256": submission.sha256,
        "size_bytes": submission.size_bytes,
        "status": SUBMISSION_UPLOADED,
        "warning": submission.warning,
        "created_at": now,
        "updated_at": now,
        "team_name": submission.team_name_snapshot,
        "racer_name": submission.display_name_snapshot,
    }
    with closing(connect(db_path)) as connection:
        table_columns = {row["name"] for row in connection.execute("PRAGMA table_info(submissions)").fetchall()}
        columns = [
            column for column in values
            if column in table_columns
        ]
        placeholders = ", ".join("?" for _ in columns)
        cursor = connection.execute(
            f"INSERT INTO submissions ({', '.join(columns)}) VALUES ({placeholders})",
            tuple(values[column] for column in columns),
        )
        connection.commit()
        return int(cursor.lastrowid)


def list_submissions(db_path: Path, *, user_id: int | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM submissions"
    params: tuple[Any, ...] = ()
    if user_id is not None:
        sql += " WHERE user_id = ?"
        params = (user_id,)
    sql += " ORDER BY id DESC"
    with closing(connect(db_path)) as connection:
        rows = connection.execute(sql, params).fetchall()
        return [_submission_row_to_dict(row) for row in rows]


def _submission_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    submission = dict(row)
    submission["team_name"] = submission.get("team_name_snapshot") or submission.get("team_name") or ""
    submission["racer_name"] = submission.get("display_name_snapshot") or submission.get("racer_name") or ""
    return submission


def get_submission(db_path: Path, submission_id: int) -> dict[str, Any] | None:
    with closing(connect(db_path)) as connection:
        row = connection.execute("SELECT * FROM submissions WHERE id = ?", (submission_id,)).fetchone()
        return None if row is None else _submission_row_to_dict(row)


def approve_submission(db_path: Path, submission_id: int) -> None:
    submission = get_submission(db_path, submission_id)
    if submission is None:
        raise GatewayStateError("Submission not found")
    if submission["status"] in {SUBMISSION_DISPATCHING, SUBMISSION_INSTALLED}:
        raise GatewayStateError("Submission cannot be approved in its current state")
    _update_submission(db_path, submission_id, SUBMISSION_APPROVED, reject_reason=None, failure_reason=None)


def reject_submission(db_path: Path, submission_id: int, reason: str) -> None:
    submission = get_submission(db_path, submission_id)
    if submission is None:
        raise GatewayStateError("Submission not found")
    if submission["status"] == SUBMISSION_DISPATCHING:
        raise GatewayStateError("Submission is currently dispatching")
    _update_submission(db_path, submission_id, SUBMISSION_REJECTED, reject_reason=reason)


def update_submission_status(db_path: Path, submission_id: int, status: str, message: str | None = None) -> None:
    if status == SUBMISSION_FAILED:
        _update_submission(db_path, submission_id, status, failure_reason=message)
    else:
        _update_submission(db_path, submission_id, status)


def _update_submission(
    db_path: Path,
    submission_id: int,
    status: str,
    *,
    reject_reason: str | None | object = _UNSET,
    failure_reason: str | None | object = _UNSET,
) -> None:
    assignments = ["status = ?", "updated_at = ?"]
    params: list[Any] = [status, utc_now()]
    if reject_reason is not _UNSET:
        assignments.append("reject_reason = ?")
        params.append(reject_reason)
    if failure_reason is not _UNSET:
        assignments.append("failure_reason = ?")
        params.append(failure_reason)
    params.append(submission_id)
    with closing(connect(db_path)) as connection:
        connection.execute(
            f"UPDATE submissions SET {', '.join(assignments)} WHERE id = ?",
            tuple(params),
        )
        connection.commit()


def create_vehicle(
    db_path: Path,
    name: str,
    console_url: str = "",
    console_password: str | None = None,
    *,
    credential_secret: str = "",
    delivery_mode: str = DISPATCH_MODE_AUTO,
    ssh_host: str = "",
    ssh_port: int = 22,
    ssh_username: str = "",
    ssh_password: str | None = None,
    ssh_private_key_path: str = "",
    ssh_remote_artifact_root: str = "/opt/aws/deepracer/artifacts",
    ssh_install_command_template: str = "",
    notes: str = "",
) -> int:
    if delivery_mode not in DISPATCH_MODES:
        raise GatewayStateError("Invalid vehicle delivery mode")
    now = utc_now()
    codec = CredentialCodec(credential_secret)
    normalized_url = console_url.rstrip("/")
    with closing(connect(db_path)) as connection:
        cursor = connection.execute(
            """
            INSERT INTO vehicles (
                name, console_url, console_password_encrypted, delivery_mode, ssh_host,
                ssh_port, ssh_username, ssh_password_encrypted, ssh_private_key_path,
                ssh_remote_artifact_root, ssh_install_command_template, notes, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                console_url = excluded.console_url,
                console_password_encrypted = excluded.console_password_encrypted,
                delivery_mode = excluded.delivery_mode,
                ssh_host = excluded.ssh_host,
                ssh_port = excluded.ssh_port,
                ssh_username = excluded.ssh_username,
                ssh_password_encrypted = excluded.ssh_password_encrypted,
                ssh_private_key_path = excluded.ssh_private_key_path,
                ssh_remote_artifact_root = excluded.ssh_remote_artifact_root,
                ssh_install_command_template = excluded.ssh_install_command_template,
                notes = excluded.notes,
                updated_at = excluded.updated_at
            """,
            (
                name.strip(),
                normalized_url,
                codec.encrypt(console_password),
                delivery_mode,
                ssh_host.strip(),
                ssh_port or 22,
                ssh_username.strip(),
                codec.encrypt(ssh_password),
                ssh_private_key_path.strip(),
                ssh_remote_artifact_root.strip() or "/opt/aws/deepracer/artifacts",
                ssh_install_command_template.strip(),
                notes.strip(),
                now,
                now,
            ),
        )
        connection.commit()
        if cursor.lastrowid:
            return int(cursor.lastrowid)
        row = connection.execute("SELECT id FROM vehicles WHERE name = ?", (name.strip(),)).fetchone()
        return int(row["id"])


def list_vehicles(db_path: Path) -> list[dict[str, Any]]:
    with closing(connect(db_path)) as connection:
        rows = connection.execute("SELECT * FROM vehicles ORDER BY name").fetchall()
        return [_vehicle_row_to_dict(row) for row in rows]


def get_vehicle(db_path: Path, vehicle_id: int) -> dict[str, Any] | None:
    with closing(connect(db_path)) as connection:
        row = connection.execute("SELECT * FROM vehicles WHERE id = ?", (vehicle_id,)).fetchone()
        return None if row is None else _vehicle_row_to_dict(row)


def _vehicle_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    vehicle = dict(row)
    vehicle["has_console_password"] = bool(vehicle.get("console_password_encrypted"))
    vehicle["has_ssh_password"] = bool(vehicle.get("ssh_password_encrypted"))
    vehicle["has_ssh_key"] = bool(vehicle.get("ssh_private_key_path"))
    vehicle["ssh_configured"] = bool(vehicle.get("ssh_host") and vehicle.get("ssh_username"))
    return vehicle


def create_dispatch_if_available(
    db_path: Path,
    submission_id: int,
    vehicle_id: int,
    *,
    requested_mode: str = DISPATCH_MODE_AUTO,
) -> int:
    if requested_mode not in DISPATCH_MODES:
        raise GatewayStateError("Invalid dispatch mode")
    now = utc_now()
    connection = connect(db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        submission = connection.execute("SELECT * FROM submissions WHERE id = ?", (submission_id,)).fetchone()
        if submission is None:
            raise GatewayStateError("Submission not found")
        if submission["status"] not in {SUBMISSION_APPROVED, SUBMISSION_INSTALLED, SUBMISSION_FAILED}:
            raise GatewayStateError("Submission must be approved before dispatch")
        vehicle = connection.execute("SELECT * FROM vehicles WHERE id = ?", (vehicle_id,)).fetchone()
        if vehicle is None:
            raise GatewayStateError("Vehicle not found")
        active_vehicle = connection.execute(
            """
            SELECT id FROM dispatches
            WHERE vehicle_id = ? AND status IN (?, ?, ?, ?)
            LIMIT 1
            """,
            (vehicle_id, *ACTIVE_DISPATCH_STATUSES),
        ).fetchone()
        if active_vehicle is not None:
            raise VehicleBusyError("Vehicle already has an active dispatch")
        cursor = connection.execute(
            """
            INSERT INTO dispatches (submission_id, vehicle_id, requested_mode, status, message, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (submission_id, vehicle_id, requested_mode, DISPATCH_QUEUED, "Queued for dispatch", now, now),
        )
        connection.execute(
            "UPDATE submissions SET status = ?, updated_at = ? WHERE id = ?",
            (SUBMISSION_DISPATCHING, now, submission_id),
        )
        connection.commit()
        return int(cursor.lastrowid)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def update_dispatch_status(db_path: Path, dispatch_id: int, status: str, message: str) -> None:
    now = utc_now()
    started_at = now if status == DISPATCH_UPLOADING else None
    finished_at = now if status in {DISPATCH_INSTALLED, DISPATCH_FAILED, DISPATCH_CANCELLED} else None
    with closing(connect(db_path)) as connection:
        if started_at is not None:
            connection.execute(
                """
                UPDATE dispatches
                SET status = ?, message = ?, started_at = COALESCE(started_at, ?), updated_at = ?
                WHERE id = ?
                """,
                (status, message, started_at, now, dispatch_id),
            )
        elif finished_at is not None:
            connection.execute(
                """
                UPDATE dispatches
                SET status = ?, message = ?, finished_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, message, finished_at, now, dispatch_id),
            )
        else:
            connection.execute(
                "UPDATE dispatches SET status = ?, message = ?, updated_at = ? WHERE id = ?",
                (status, message, now, dispatch_id),
            )
        connection.commit()


def cancel_dispatch(db_path: Path, dispatch_id: int) -> None:
    dispatch = get_dispatch(db_path, dispatch_id)
    if dispatch is None:
        raise GatewayStateError("Dispatch not found")
    if dispatch["status"] != DISPATCH_QUEUED:
        with closing(connect(db_path)) as connection:
            connection.execute("UPDATE dispatches SET cancel_requested = 1, updated_at = ? WHERE id = ?", (utc_now(), dispatch_id))
            connection.commit()
        return
    update_dispatch_status(db_path, dispatch_id, DISPATCH_CANCELLED, "Dispatch cancelled")
    update_submission_status(db_path, int(dispatch["submission_id"]), SUBMISSION_APPROVED)


def get_dispatch(db_path: Path, dispatch_id: int) -> dict[str, Any] | None:
    with closing(connect(db_path)) as connection:
        return row_to_dict(connection.execute("SELECT * FROM dispatches WHERE id = ?", (dispatch_id,)).fetchone())


def list_dispatches(db_path: Path, limit: int = 25) -> list[dict[str, Any]]:
    with closing(connect(db_path)) as connection:
        rows = connection.execute(
            """
            SELECT
                d.*,
                s.team_name_snapshot AS team_name,
                s.display_name_snapshot AS racer_name,
                s.model_name,
                v.name AS vehicle_name
            FROM dispatches d
            JOIN submissions s ON s.id = d.submission_id
            JOIN vehicles v ON v.id = d.vehicle_id
            ORDER BY d.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]


def start_dispatch_attempt(db_path: Path, dispatch_id: int, mode: str, message: str) -> int:
    now = utc_now()
    with closing(connect(db_path)) as connection:
        cursor = connection.execute(
            """
            INSERT INTO dispatch_attempts (dispatch_id, mode, status, message, started_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (dispatch_id, mode, DISPATCH_UPLOADING, message, now),
        )
        connection.commit()
        return int(cursor.lastrowid)


def finish_dispatch_attempt(db_path: Path, attempt_id: int, status: str, message: str) -> None:
    with closing(connect(db_path)) as connection:
        connection.execute(
            "UPDATE dispatch_attempts SET status = ?, message = ?, finished_at = ? WHERE id = ?",
            (status, message, utc_now(), attempt_id),
        )
        connection.commit()


def list_dispatch_attempts(db_path: Path, dispatch_id: int) -> list[dict[str, Any]]:
    with closing(connect(db_path)) as connection:
        rows = connection.execute(
            "SELECT * FROM dispatch_attempts WHERE dispatch_id = ? ORDER BY id",
            (dispatch_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_dispatch_context(db_path: Path, dispatch_id: int, *, credential_secret: str = "") -> dict[str, Any] | None:
    with closing(connect(db_path)) as connection:
        row = connection.execute(
            """
            SELECT
                d.id AS dispatch_id,
                d.status AS dispatch_status,
                d.requested_mode,
                d.cancel_requested,
                s.id AS submission_id,
                s.storage_path,
                s.original_filename,
                s.model_name,
                v.id AS vehicle_id,
                v.name AS vehicle_name,
                v.console_url,
                v.console_password_encrypted,
                v.delivery_mode,
                v.ssh_host,
                v.ssh_port,
                v.ssh_username,
                v.ssh_password_encrypted,
                v.ssh_private_key_path,
                v.ssh_remote_artifact_root,
                v.ssh_install_command_template
            FROM dispatches d
            JOIN submissions s ON s.id = d.submission_id
            JOIN vehicles v ON v.id = d.vehicle_id
            WHERE d.id = ?
            """,
            (dispatch_id,),
        ).fetchone()
        if row is None:
            return None
    context = dict(row)
    codec = CredentialCodec(credential_secret)
    context["console_password"] = codec.decrypt(context.get("console_password_encrypted"))
    context["ssh_password"] = codec.decrypt(context.get("ssh_password_encrypted"))
    return context


def team_members_snapshot(team: dict[str, Any]) -> str:
    members = [
        {"username": member["username"], "display_name": member["display_name"], "role": member["role"]}
        for member in team.get("members", [])
    ]
    return json.dumps(members, ensure_ascii=False)
