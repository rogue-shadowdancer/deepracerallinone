from __future__ import annotations

from pathlib import Path

import pytest

from model_gateway.storage import UploadValidationError, model_folder_name, validate_model_archive

from conftest import make_model_tar


def test_validate_model_archive_accepts_physical_model(tmp_path: Path) -> None:
    archive = make_model_tar(tmp_path / "model.tar.gz")

    result = validate_model_archive(archive)

    assert result.warning is None


def test_validate_model_archive_rejects_unsafe_path(tmp_path: Path) -> None:
    archive = make_model_tar(tmp_path / "model.tar.gz", unsafe_name="../bad.txt")

    with pytest.raises(UploadValidationError, match="Unsafe archive path"):
        validate_model_archive(archive)


def test_validate_model_archive_requires_metadata(tmp_path: Path) -> None:
    archive = make_model_tar(tmp_path / "model.tar.gz", include_metadata=False)

    with pytest.raises(UploadValidationError, match="model_metadata.json"):
        validate_model_archive(archive)


def test_model_folder_name_requires_tar_gz() -> None:
    assert model_folder_name("physicalmodel-car.tar.gz") == "physicalmodel-car"
    with pytest.raises(UploadValidationError):
        model_folder_name("model.zip")
