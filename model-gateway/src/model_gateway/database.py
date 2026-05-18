from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SUBMISSION_UPLOADED = "uploaded"
SUBMISSION_APPROVED = "approved"
SUBMISSION_REJECTED = "rejected"
SUBMISSION_DISPATCHING = "dispatching"
SUBMISSION_INSTALLED = "installed"
SUBMISSION_FAILED = "failed"

DISPATCH_QUEUED = "queued"
DISPATCH_UPLOADING = "uploading"
DISPATCH_INSTALLING = "installing"
DISPATCH_INSTALLED = "installed"
DISPATCH_FAILED = "failed"

ACTIVE_DISPATCH_STATUSES = (DISPATCH_QUEUED, DISPATCH_UPLOADING, DISPATCH_INSTALLING)


class GatewayStateError(ValueError):
    """Raised when a requested state transition is invalid."""


class VehicleBusyError(GatewayStateError):
    """Raised when a vehicle already has an active dispatch."""


@dataclass(frozen=True)
class NewSubmission:
    team_name: str
    racer_name: str
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
    if row is None:
        return None
    return dict(row)


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(db_path)) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_name TEXT NOT NULL,
                racer_name TEXT NOT NULL,
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
                console_url TEXT NOT NULL,
                console_password TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS dispatches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                submission_id INTEGER NOT NULL REFERENCES submissions(id),
                vehicle_id INTEGER NOT NULL REFERENCES vehicles(id),
                status TEXT NOT NULL,
                message TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_submissions_status ON submissions(status);
            CREATE INDEX IF NOT EXISTS idx_dispatches_vehicle_status ON dispatches(vehicle_id, status);
            """
        )
        connection.commit()


def create_submission(db_path: Path, submission: NewSubmission) -> int:
    now = utc_now()
    with closing(connect(db_path)) as connection:
        cursor = connection.execute(
            """
            INSERT INTO submissions (
                team_name, racer_name, model_name, notes, original_filename, storage_path,
                sha256, size_bytes, status, warning, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                submission.team_name,
                submission.racer_name,
                submission.model_name,
                submission.notes,
                submission.original_filename,
                submission.storage_path,
                submission.sha256,
                submission.size_bytes,
                SUBMISSION_UPLOADED,
                submission.warning,
                now,
                now,
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)


def list_submissions(db_path: Path) -> list[dict[str, Any]]:
    with closing(connect(db_path)) as connection:
        rows = connection.execute(
            "SELECT * FROM submissions ORDER BY id DESC"
        ).fetchall()
        return [dict(row) for row in rows]


def get_submission(db_path: Path, submission_id: int) -> dict[str, Any] | None:
    with closing(connect(db_path)) as connection:
        return row_to_dict(
            connection.execute("SELECT * FROM submissions WHERE id = ?", (submission_id,)).fetchone()
        )


def approve_submission(db_path: Path, submission_id: int) -> None:
    submission = get_submission(db_path, submission_id)
    if submission is None:
        raise GatewayStateError("Submission not found")
    if submission["status"] in {SUBMISSION_DISPATCHING, SUBMISSION_INSTALLED}:
        raise GatewayStateError("Submission cannot be approved in its current state")
    with closing(connect(db_path)) as connection:
        connection.execute(
            """
            UPDATE submissions
            SET status = ?, reject_reason = NULL, failure_reason = NULL, updated_at = ?
            WHERE id = ?
            """,
            (SUBMISSION_APPROVED, utc_now(), submission_id),
        )
        connection.commit()


def reject_submission(db_path: Path, submission_id: int, reason: str) -> None:
    submission = get_submission(db_path, submission_id)
    if submission is None:
        raise GatewayStateError("Submission not found")
    if submission["status"] == SUBMISSION_DISPATCHING:
        raise GatewayStateError("Submission is currently dispatching")
    with closing(connect(db_path)) as connection:
        connection.execute(
            """
            UPDATE submissions
            SET status = ?, reject_reason = ?, updated_at = ?
            WHERE id = ?
            """,
            (SUBMISSION_REJECTED, reason, utc_now(), submission_id),
        )
        connection.commit()


def update_submission_status(db_path: Path, submission_id: int, status: str, message: str | None = None) -> None:
    field = "failure_reason" if status == SUBMISSION_FAILED else "reject_reason"
    with closing(connect(db_path)) as connection:
        if message is None:
            connection.execute(
                "UPDATE submissions SET status = ?, updated_at = ? WHERE id = ?",
                (status, utc_now(), submission_id),
            )
        else:
            connection.execute(
                f"UPDATE submissions SET status = ?, {field} = ?, updated_at = ? WHERE id = ?",
                (status, message, utc_now(), submission_id),
            )
        connection.commit()


def create_vehicle(db_path: Path, name: str, console_url: str, console_password: str | None) -> int:
    now = utc_now()
    normalized_url = console_url.rstrip("/")
    with closing(connect(db_path)) as connection:
        cursor = connection.execute(
            """
            INSERT INTO vehicles (name, console_url, console_password, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                console_url = excluded.console_url,
                console_password = excluded.console_password,
                updated_at = excluded.updated_at
            """,
            (name, normalized_url, console_password or None, now, now),
        )
        connection.commit()
        if cursor.lastrowid:
            return int(cursor.lastrowid)
        row = connection.execute("SELECT id FROM vehicles WHERE name = ?", (name,)).fetchone()
        return int(row["id"])


def list_vehicles(db_path: Path) -> list[dict[str, Any]]:
    with closing(connect(db_path)) as connection:
        rows = connection.execute("SELECT * FROM vehicles ORDER BY name").fetchall()
        return [dict(row) for row in rows]


def get_vehicle(db_path: Path, vehicle_id: int) -> dict[str, Any] | None:
    with closing(connect(db_path)) as connection:
        return row_to_dict(connection.execute("SELECT * FROM vehicles WHERE id = ?", (vehicle_id,)).fetchone())


def create_dispatch_if_available(db_path: Path, submission_id: int, vehicle_id: int) -> int:
    now = utc_now()
    connection = connect(db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        submission = connection.execute("SELECT * FROM submissions WHERE id = ?", (submission_id,)).fetchone()
        if submission is None:
            raise GatewayStateError("Submission not found")
        if submission["status"] != SUBMISSION_APPROVED:
            raise GatewayStateError("Submission must be approved before dispatch")
        vehicle = connection.execute("SELECT * FROM vehicles WHERE id = ?", (vehicle_id,)).fetchone()
        if vehicle is None:
            raise GatewayStateError("Vehicle not found")
        active = connection.execute(
            """
            SELECT id FROM dispatches
            WHERE vehicle_id = ? AND status IN (?, ?, ?)
            LIMIT 1
            """,
            (vehicle_id, *ACTIVE_DISPATCH_STATUSES),
        ).fetchone()
        if active is not None:
            raise VehicleBusyError("Vehicle already has an active dispatch")
        cursor = connection.execute(
            """
            INSERT INTO dispatches (submission_id, vehicle_id, status, message, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (submission_id, vehicle_id, DISPATCH_QUEUED, "Queued for dispatch", now, now),
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
    finished_at = now if status in {DISPATCH_INSTALLED, DISPATCH_FAILED} else None
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


def get_dispatch(db_path: Path, dispatch_id: int) -> dict[str, Any] | None:
    with closing(connect(db_path)) as connection:
        return row_to_dict(connection.execute("SELECT * FROM dispatches WHERE id = ?", (dispatch_id,)).fetchone())


def list_dispatches(db_path: Path, limit: int = 25) -> list[dict[str, Any]]:
    with closing(connect(db_path)) as connection:
        rows = connection.execute(
            """
            SELECT
                d.*,
                s.team_name,
                s.racer_name,
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


def get_dispatch_context(db_path: Path, dispatch_id: int) -> dict[str, Any] | None:
    with closing(connect(db_path)) as connection:
        row = connection.execute(
            """
            SELECT
                d.id AS dispatch_id,
                d.status AS dispatch_status,
                s.*,
                v.id AS vehicle_id,
                v.name AS vehicle_name,
                v.console_url,
                v.console_password
            FROM dispatches d
            JOIN submissions s ON s.id = d.submission_id
            JOIN vehicles v ON v.id = d.vehicle_id
            WHERE d.id = ?
            """,
            (dispatch_id,),
        ).fetchone()
        return row_to_dict(row)
