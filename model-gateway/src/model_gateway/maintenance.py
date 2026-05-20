from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from model_gateway.config import Settings
from model_gateway.database import SUBMISSION_FAILED, init_db
from model_gateway.diagnostics import run_vehicle_diagnostics


def backup(settings: Settings, destination: Path) -> Path:
    settings.ensure_directories()
    init_db(settings.db_path)
    _assert_sqlite_integrity(settings.db_path)
    destination.mkdir(parents=True, exist_ok=True)
    archive_path = destination / f"deepracer-gateway-backup-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        if settings.db_path.exists():
            archive.add(settings.db_path, arcname="gateway.sqlite3")
        if settings.upload_dir.exists():
            archive.add(settings.upload_dir, arcname="uploads")
    return archive_path


def restore(settings: Settings, archive_path: Path) -> None:
    if not archive_path.is_file():
        raise FileNotFoundError(archive_path)
    settings.ensure_directories()
    with tarfile.open(archive_path, "r:gz") as archive:
        names = set(archive.getnames())
        if "gateway.sqlite3" not in names:
            raise ValueError("Backup archive does not contain gateway.sqlite3")
        if not any(name == "uploads" or name.startswith("uploads/") for name in names):
            raise ValueError("Backup archive does not contain uploads directory")
        for member in archive.getmembers():
            if member.name.startswith("/") or ".." in Path(member.name).parts:
                raise ValueError(f"Unsafe backup path: {member.name}")
        archive.extractall(settings.data_dir)
    init_db(settings.db_path)
    _assert_sqlite_integrity(settings.db_path)


def cleanup_uploads(settings: Settings, older_than_days: int) -> int:
    preview = cleanup_preview(settings, older_than_days)
    removed = 0
    upload_root = settings.upload_dir.resolve()
    for item in preview["items"]:
        path = Path(str(item["storage_path"])).resolve()
        if path.exists() and upload_root in path.parents:
            shutil.rmtree(path.parent, ignore_errors=True)
            removed += 1
    return removed


def cleanup_preview(settings: Settings, older_than_days: int) -> dict[str, object]:
    if older_than_days < 0:
        raise ValueError("older_than_days must be non-negative")
    cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat(timespec="seconds")
    items: list[dict[str, object]] = []
    total_bytes = 0
    connection = sqlite3.connect(settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT id, model_name, storage_path, size_bytes, created_at FROM submissions WHERE status = ? AND created_at <= ?",
            (SUBMISSION_FAILED, cutoff),
        ).fetchall()
        upload_root = settings.upload_dir.resolve()
        for row in rows:
            path = Path(row["storage_path"]).resolve()
            if path.exists() and upload_root in path.parents:
                size_bytes = _directory_size(path.parent)
                total_bytes += size_bytes
                items.append(
                    {
                        "id": row["id"],
                        "model_name": row["model_name"],
                        "storage_path": str(path),
                        "size_bytes": size_bytes,
                        "created_at": row["created_at"],
                    }
                )
    finally:
        connection.close()
    return {"count": len(items), "total_bytes": total_bytes, "items": items}


def doctor(settings: Settings, vehicle_id: int) -> dict[str, object]:
    settings.ensure_directories()
    init_db(settings.db_path)
    return run_vehicle_diagnostics(settings, vehicle_id)


def _assert_sqlite_integrity(db_path: Path) -> None:
    if not db_path.exists():
        return
    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute("PRAGMA integrity_check").fetchone()
        if not row or row[0] != "ok":
            raise ValueError(f"SQLite integrity check failed: {row[0] if row else 'no result'}")
    finally:
        connection.close()


def _directory_size(path: Path) -> int:
    total = 0
    if path.is_file():
        return path.stat().st_size
    for child in path.rglob("*"):
        if child.is_file():
            total += child.stat().st_size
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="DeepRacer Model Gateway maintenance tools")
    subcommands = parser.add_subparsers(dest="command", required=True)
    backup_parser = subcommands.add_parser("backup")
    backup_parser.add_argument("destination", type=Path)
    restore_parser = subcommands.add_parser("restore")
    restore_parser.add_argument("archive", type=Path)
    cleanup_parser = subcommands.add_parser("cleanup")
    cleanup_parser.add_argument("--older-than-days", type=int, default=7)
    cleanup_parser.add_argument("--dry-run", action="store_true")
    doctor_parser = subcommands.add_parser("doctor")
    doctor_parser.add_argument("--vehicle-id", type=int, required=True)
    args = parser.parse_args()
    settings = Settings()
    if args.command == "backup":
        print(backup(settings, args.destination))
    elif args.command == "restore":
        restore(settings, args.archive)
    elif args.command == "cleanup":
        if args.dry_run:
            print(json.dumps(cleanup_preview(settings, args.older_than_days), ensure_ascii=False, indent=2))
        else:
            print(cleanup_uploads(settings, args.older_than_days))
    elif args.command == "doctor":
        print(json.dumps(doctor(settings, args.vehicle_id), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
