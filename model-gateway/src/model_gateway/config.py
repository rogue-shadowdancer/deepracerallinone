from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value == "":
        return default
    return int(raw_value)


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("GATEWAY_DATA_DIR", "data")))
    session_secret: str = field(default_factory=lambda: os.getenv("GATEWAY_SESSION_SECRET", "dev-secret-change-me"))
    bootstrap_admin_username: str = field(default_factory=lambda: os.getenv("GATEWAY_BOOTSTRAP_ADMIN_USERNAME", "admin"))
    bootstrap_admin_password: str = field(
        default_factory=lambda: os.getenv(
            "GATEWAY_BOOTSTRAP_ADMIN_PASSWORD",
            os.getenv("GATEWAY_ADMIN_PASSWORD", "admin"),
        )
    )
    credential_secret: str = field(default_factory=lambda: os.getenv("GATEWAY_CREDENTIAL_SECRET", ""))
    max_upload_bytes: int = field(default_factory=lambda: _int_env("GATEWAY_MAX_UPLOAD_BYTES", 1024 * 1024 * 1024))
    vehicle_timeout_seconds: int = field(default_factory=lambda: _int_env("GATEWAY_VEHICLE_TIMEOUT_SECONDS", 30))
    install_timeout_seconds: int = field(default_factory=lambda: _int_env("GATEWAY_INSTALL_TIMEOUT_SECONDS", 180))
    install_poll_seconds: int = field(default_factory=lambda: _int_env("GATEWAY_INSTALL_POLL_SECONDS", 3))
    ssh_timeout_seconds: int = field(default_factory=lambda: _int_env("GATEWAY_SSH_TIMEOUT_SECONDS", 20))
    ssh_retry_count: int = field(default_factory=lambda: _int_env("GATEWAY_SSH_RETRY_COUNT", 3))
    ssh_chunk_bytes: int = field(default_factory=lambda: _int_env("GATEWAY_SSH_CHUNK_BYTES", 1024 * 1024))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "gateway.sqlite3"

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
