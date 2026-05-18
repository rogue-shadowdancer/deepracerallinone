from __future__ import annotations

import hashlib
import os
import shutil
import tarfile
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from fastapi import UploadFile


class UploadValidationError(ValueError):
    """Raised when an uploaded model file is invalid."""


@dataclass(frozen=True)
class ArchiveValidation:
    warning: str | None = None


@dataclass(frozen=True)
class StoredUpload:
    original_filename: str
    storage_path: Path
    sha256: str
    size_bytes: int
    warning: str | None = None


def sanitize_filename(filename: str) -> str:
    name = filename.replace("\\", "/").split("/")[-1].strip()
    if not name:
        raise UploadValidationError("Upload must include a filename")
    return name


def model_folder_name(filename: str) -> str:
    if not filename.endswith(".tar.gz"):
        raise UploadValidationError("Model file must end with .tar.gz")
    return filename[:-7]


def _is_safe_tar_name(name: str) -> bool:
    if not name or "\\" in name:
        return False
    path = PurePosixPath(name)
    if path.is_absolute():
        return False
    if any(part in {"", ".", ".."} for part in path.parts):
        return False
    first_part = path.parts[0] if path.parts else ""
    if ":" in first_part:
        return False
    return True


def validate_model_archive(path: Path) -> ArchiveValidation:
    has_metadata = False
    has_pb = False
    try:
        with tarfile.open(path, "r:gz") as archive:
            for member in archive.getmembers():
                if not _is_safe_tar_name(member.name):
                    raise UploadValidationError(f"Unsafe archive path: {member.name}")
                if member.issym() or member.islnk():
                    raise UploadValidationError(f"Archive links are not allowed: {member.name}")
                member_name = PurePosixPath(member.name).name
                if member_name == "model_metadata.json":
                    has_metadata = True
                if member_name.endswith(".pb"):
                    has_pb = True
    except tarfile.TarError as exc:
        raise UploadValidationError("Model file is not a readable .tar.gz archive") from exc

    if not has_metadata:
        raise UploadValidationError("Model archive must include model_metadata.json")
    if not has_pb:
        return ArchiveValidation(
            warning="No .pb model file was found. The vehicle may reject this archive if it is not a physical model export."
        )
    return ArchiveValidation()


async def save_upload(upload: UploadFile, upload_dir: Path, max_upload_bytes: int) -> StoredUpload:
    original_filename = sanitize_filename(upload.filename or "")
    model_folder_name(original_filename)

    submission_id = uuid.uuid4().hex
    submission_dir = upload_dir / submission_id
    submission_dir.mkdir(parents=True, exist_ok=False)
    storage_path = submission_dir / original_filename
    digest = hashlib.sha256()
    size = 0

    try:
        with storage_path.open("wb") as output:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_upload_bytes:
                    raise UploadValidationError("Model file exceeds the configured upload size limit")
                digest.update(chunk)
                output.write(chunk)
        if size == 0:
            raise UploadValidationError("Model file is empty")
        validation = validate_model_archive(storage_path)
        return StoredUpload(
            original_filename=original_filename,
            storage_path=storage_path,
            sha256=digest.hexdigest(),
            size_bytes=size,
            warning=validation.warning,
        )
    except Exception:
        shutil.rmtree(submission_dir, ignore_errors=True)
        raise
    finally:
        await upload.close()


def archive_size(path: Path) -> int:
    return os.stat(path).st_size
