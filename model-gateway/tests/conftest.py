from __future__ import annotations

import io
import json
import sys
import tarfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from model_gateway.app import create_app
from model_gateway.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        bootstrap_admin_username="admin",
        bootstrap_admin_password="test-admin",
        session_secret="test-secret",
        credential_secret="test-credential-secret",
        max_upload_bytes=1024 * 1024,
        install_timeout_seconds=1,
        install_poll_seconds=0,
        ssh_retry_count=1,
        ssh_chunk_bytes=128,
    )


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


def make_model_tar(path: Path, *, unsafe_name: str | None = None, include_metadata: bool = True, include_pb: bool = True) -> Path:
    with tarfile.open(path, "w:gz") as archive:
        if unsafe_name:
            payload = b"unsafe"
            info = tarfile.TarInfo(unsafe_name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
        if include_metadata:
            metadata = json.dumps({"sensor": ["FRONT_FACING_CAMERA"], "action_space": []}).encode("utf-8")
            info = tarfile.TarInfo("model_metadata.json")
            info.size = len(metadata)
            archive.addfile(info, io.BytesIO(metadata))
        if include_pb:
            payload = b"fake-model"
            info = tarfile.TarInfo("model.pb")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return path
