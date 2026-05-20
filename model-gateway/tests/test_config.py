from __future__ import annotations

from pathlib import Path

import pytest

from model_gateway.config import Settings


def test_competition_mode_rejects_default_secrets(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, competition_mode=True)

    with pytest.raises(ValueError, match="Competition mode"):
        settings.validate_runtime()


def test_competition_mode_accepts_explicit_secrets(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        competition_mode=True,
        bootstrap_admin_username="race-admin",
        bootstrap_admin_password="race-admin-password",
        session_secret="session-secret",
        credential_secret="credential-secret",
        allow_insecure_lan_cookie=True,
    )

    settings.validate_runtime()


def test_competition_mode_requires_secure_or_explicit_lan_cookie(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        competition_mode=True,
        bootstrap_admin_username="race-admin",
        bootstrap_admin_password="race-admin-password",
        session_secret="session-secret",
        credential_secret="credential-secret",
        cookie_secure=False,
        allow_insecure_lan_cookie=False,
    )

    with pytest.raises(ValueError, match="GATEWAY_COOKIE_SECURE"):
        settings.validate_runtime()
