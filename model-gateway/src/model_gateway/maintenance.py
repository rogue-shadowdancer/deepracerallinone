from __future__ import annotations

import argparse
import shutil
import sqlite3
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from model_gateway.config import Settings
from model_gateway.database import SUBMISSION_FAILED, init_db


def backup(settings: Settings, destination: Path) -> Path:
    settings.ensure_directories()
    init_db(settings.db_path)
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
        for member in archive.getmembers():
            if member.name.startswith("/") or ".." in Path(member.name).parts:
                raise ValueError(f"Unsafe backup path: {member.name}")
        archive.extractall(settings.data_dir)
    init_db(settings.db_path)


def cleanup_uploads(settings: Settings, older_than_days: int) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat(timespec="seconds")
    removed = 0
    connection = sqlite3.connect(settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT id, storage_path FROM submissions WHERE status = ? AND created_at < ?",
            (SUBMISSION_FAILED, cutoff),
        ).fetchall()
        upload_root = settings.upload_dir.resolve()
        for row in rows:
            path = Path(row["storage_path"]).resolve()
            if path.exists() and upload_root in path.parents:
                shutil.rmtree(path.parent, ignore_errors=True)
                removed += 1
    finally:
        connection.close()
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(description="DeepRacer Model Gateway maintenance tools")
    subcommands = parser.add_subparsers(dest="command", required=True)
    backup_parser = subcommands.add_parser("backup")
    backup_parser.add_argument("destination", type=Path)
    restore_parser = subcommands.add_parser("restore")
    restore_parser.add_argument("archive", type=Path)
    cleanup_parser = subcommands.add_parser("cleanup")
    cleanup_parser.add_argument("--older-than-days", type=int, default=7)
    args = parser.parse_args()
    settings = Settings()
    if args.command == "backup":
        print(backup(settings, args.destination))
    elif args.command == "restore":
        restore(settings, args.archive)
    elif args.command == "cleanup":
        print(cleanup_uploads(settings, args.older_than_days))


if __name__ == "__main__":
    main()
