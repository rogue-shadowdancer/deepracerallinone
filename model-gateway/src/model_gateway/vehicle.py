from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx

from model_gateway.storage import model_folder_name


class VehicleClientError(RuntimeError):
    """Raised when the DeepRacer vehicle API cannot complete a model install."""


@dataclass(frozen=True)
class VehicleInstallResult:
    folder_name: str
    upload_message: str


class VehicleClient:
    def __init__(
        self,
        console_url: str,
        password: str | None = None,
        *,
        timeout_seconds: int = 30,
        install_timeout_seconds: int = 180,
        poll_seconds: int = 3,
        transport: httpx.BaseTransport | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.console_url = console_url.rstrip("/")
        self.password = password
        self.install_timeout_seconds = install_timeout_seconds
        self.poll_seconds = poll_seconds
        self.sleeper = sleeper
        self._csrf_token: str | None = None
        self.client = httpx.Client(
            base_url=self.console_url,
            timeout=timeout_seconds,
            follow_redirects=True,
            transport=transport,
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "VehicleClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        self.close()

    def login(self) -> None:
        if not self.password:
            return
        login_page = self.client.get("/login")
        if login_page.status_code < 500:
            self._csrf_token = self._extract_csrf_token(login_page.text)
        data = {"password": self.password}
        headers = self._csrf_headers()
        if self._csrf_token:
            data["csrf_token"] = self._csrf_token
        response = self.client.post("/login", data=data, headers=headers)
        if response.status_code >= 400:
            raise VehicleClientError(f"Vehicle console login failed with HTTP {response.status_code}")

    def upload_model(self, model_path: Path, upload_filename: str) -> str:
        if not model_path.is_file():
            raise VehicleClientError(f"Model file not found: {model_path}")
        headers = self._csrf_headers()
        with model_path.open("rb") as model_file:
            response = self.client.post(
                "/api/uploadModels",
                files={"file": (upload_filename, model_file, "application/gzip")},
                headers=headers,
            )
        if response.status_code >= 400:
            raise VehicleClientError(f"Vehicle upload failed with HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise VehicleClientError("Vehicle upload response was not JSON") from exc
        if not payload.get("success"):
            raise VehicleClientError(str(payload.get("message") or "Vehicle rejected the model upload"))
        return str(payload.get("message") or "Model uploaded")

    def wait_until_installed(self, folder_name: str) -> None:
        deadline = time.monotonic() + self.install_timeout_seconds
        last_status = "waiting"
        while time.monotonic() <= deadline:
            if self.is_model_installed(folder_name):
                return
            last_status = self.model_loading_status()
            if last_status == "error":
                raise VehicleClientError("Vehicle reported model loading error")
            self.sleeper(float(self.poll_seconds))
        raise VehicleClientError(f"Timed out waiting for vehicle install; last status: {last_status}")

    def install_model(self, model_path: Path, upload_filename: str) -> VehicleInstallResult:
        folder_name = model_folder_name(upload_filename)
        self.login()
        upload_message = self.upload_model(model_path, upload_filename)
        self.wait_until_installed(folder_name)
        return VehicleInstallResult(folder_name=folder_name, upload_message=upload_message)

    def is_model_installed(self, folder_name: str) -> bool:
        response = self.client.get("/api/is_model_installed", params={"filename": folder_name})
        if response.status_code >= 400:
            return False
        try:
            payload = response.json()
        except ValueError:
            return False
        return bool(payload.get("success"))

    def model_loading_status(self) -> str:
        response = self.client.get("/api/isModelLoading")
        if response.status_code >= 400:
            return "unknown"
        try:
            payload = response.json()
        except ValueError:
            return "unknown"
        return str(payload.get("isModelLoading") or "unknown")

    def _csrf_headers(self) -> dict[str, str]:
        if not self._csrf_token:
            return {}
        return {"X-CSRFToken": self._csrf_token}

    @staticmethod
    def _extract_csrf_token(html: str) -> str | None:
        match = re.search(r'name=["\']csrf_token["\'][^>]*value=["\']([^"\']+)["\']', html)
        if match:
            return match.group(1)
        return None
