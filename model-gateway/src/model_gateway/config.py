from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _bool_env(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value == "":
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


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
    competition_mode: bool = field(default_factory=lambda: _bool_env("GATEWAY_COMPETITION_MODE", False))
    cookie_secure: bool = field(default_factory=lambda: _bool_env("GATEWAY_COOKIE_SECURE", False))
    allow_insecure_lan_cookie: bool = field(default_factory=lambda: _bool_env("GATEWAY_ALLOW_INSECURE_LAN_COOKIE", False))
    session_max_age_seconds: int = field(default_factory=lambda: _int_env("GATEWAY_SESSION_MAX_AGE_SECONDS", 8 * 60 * 60))
    login_rate_limit: int = field(default_factory=lambda: _int_env("GATEWAY_LOGIN_RATE_LIMIT", 5))
    login_lockout_seconds: int = field(default_factory=lambda: _int_env("GATEWAY_LOGIN_LOCKOUT_SECONDS", 10 * 60))
    max_upload_bytes: int = field(default_factory=lambda: _int_env("GATEWAY_MAX_UPLOAD_BYTES", 1024 * 1024 * 1024))
    vehicle_timeout_seconds: int = field(default_factory=lambda: _int_env("GATEWAY_VEHICLE_TIMEOUT_SECONDS", 30))
    install_timeout_seconds: int = field(default_factory=lambda: _int_env("GATEWAY_INSTALL_TIMEOUT_SECONDS", 180))
    install_poll_seconds: int = field(default_factory=lambda: _int_env("GATEWAY_INSTALL_POLL_SECONDS", 3))
    ssh_timeout_seconds: int = field(default_factory=lambda: _int_env("GATEWAY_SSH_TIMEOUT_SECONDS", 20))
    ssh_retry_count: int = field(default_factory=lambda: _int_env("GATEWAY_SSH_RETRY_COUNT", 3))
    ssh_chunk_bytes: int = field(default_factory=lambda: _int_env("GATEWAY_SSH_CHUNK_BYTES", 1024 * 1024))
    dispatch_worker_enabled: bool = field(default_factory=lambda: _bool_env("GATEWAY_DISPATCH_WORKER_ENABLED", True))
    dispatch_worker_poll_seconds: int = field(default_factory=lambda: _int_env("GATEWAY_DISPATCH_WORKER_POLL_SECONDS", 2))
    dispatch_max_retries: int = field(default_factory=lambda: _int_env("GATEWAY_DISPATCH_MAX_RETRIES", 1))
    dispatch_retry_delay_seconds: int = field(default_factory=lambda: _int_env("GATEWAY_DISPATCH_RETRY_DELAY_SECONDS", 30))
    stuck_dispatch_seconds: int = field(default_factory=lambda: _int_env("GATEWAY_STUCK_DISPATCH_SECONDS", 15 * 60))
    auto_backup_enabled: bool = field(default_factory=lambda: _bool_env("GATEWAY_AUTO_BACKUP_ENABLED", True))
    support_bundle_log_lines: int = field(default_factory=lambda: _int_env("GATEWAY_SUPPORT_BUNDLE_LOG_LINES", 200))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "gateway.sqlite3"

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "backups"

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def validate_runtime(self) -> None:
        if self.session_max_age_seconds <= 0:
            raise ValueError("GATEWAY_SESSION_MAX_AGE_SECONDS must be positive")
        if self.login_rate_limit <= 0:
            raise ValueError("GATEWAY_LOGIN_RATE_LIMIT must be positive")
        if not self.competition_mode:
            return
        if self.bootstrap_admin_username == "admin" and self.bootstrap_admin_password == "admin":
            raise ValueError("Competition mode cannot use the default admin/admin bootstrap account")
        if self.session_secret in {"", "dev-secret-change-me"}:
            raise ValueError("Competition mode requires a non-default GATEWAY_SESSION_SECRET")
        if not self.credential_secret:
            raise ValueError("Competition mode requires GATEWAY_CREDENTIAL_SECRET")
        if not self.cookie_secure and not self.allow_insecure_lan_cookie:
            raise ValueError(
                "Competition mode requires GATEWAY_COOKIE_SECURE=true or explicit "
                "GATEWAY_ALLOW_INSECURE_LAN_COOKIE=true for HTTP-only LAN deployments"
            )
