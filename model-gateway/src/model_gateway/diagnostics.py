from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from model_gateway.config import Settings
from model_gateway.database import (
    DIAGNOSTIC_ERROR,
    DIAGNOSTIC_READY,
    DIAGNOSTIC_WARNING,
    get_vehicle,
    record_vehicle_diagnostic,
    record_vehicle_health_check,
)
from model_gateway.security import CredentialCodec
from model_gateway.ssh_delivery import SshDeliveryClient
from model_gateway.vehicle import VehicleClient


VehicleClientFactory = Callable[..., VehicleClient]
SshClientFactory = Callable[..., SshDeliveryClient]


def run_vehicle_diagnostics(
    settings: Settings,
    vehicle_id: int,
    *,
    client_factory: VehicleClientFactory = VehicleClient,
    ssh_client_factory: SshClientFactory = SshDeliveryClient,
) -> dict[str, object]:
    vehicle = get_vehicle(settings.db_path, vehicle_id)
    if vehicle is None:
        raise ValueError("Vehicle not found")

    codec = CredentialCodec(settings.credential_secret)
    steps: list[dict[str, object]] = []
    snapshot: dict[str, object] = {
        "vehicle_id": vehicle_id,
        "vehicle_name": vehicle["name"],
        "delivery_mode": vehicle["delivery_mode"],
        "console_url_configured": bool(vehicle.get("console_url")),
        "ssh_configured": bool(vehicle.get("ssh_host") and vehicle.get("ssh_username")),
        "ssh_host_key_configured": bool(vehicle.get("ssh_host_key_sha256")),
        "upload_endpoint_response_shape": "not_exercised_without_test_model",
    }

    console_status = "skipped"
    ssh_status = "skipped"
    rsync_status = "unknown"
    disk_free_bytes = None

    if vehicle.get("console_url"):
        client = client_factory(
            vehicle["console_url"],
            codec.decrypt(vehicle.get("console_password_encrypted")),
            timeout_seconds=settings.vehicle_timeout_seconds,
            install_timeout_seconds=settings.install_timeout_seconds,
            poll_seconds=settings.install_poll_seconds,
        )
        try:
            _capture_step(steps, "console_login", lambda: client.login(), "Check vehicle Console URL and password.")
            snapshot["console_csrf_token_present"] = bool(getattr(client, "_csrf_token", None))
            loading = _capture_step(
                steps,
                "console_model_loading_status",
                client.model_loading_status,
                "Verify the vehicle webserver exposes /api/isModelLoading.",
            )
            snapshot["is_model_loading_response"] = loading
            installed = _capture_step(
                steps,
                "console_is_model_installed_shape",
                lambda: client.is_model_installed("__gateway_diagnostic__"),
                "Verify /api/is_model_installed is reachable.",
            )
            snapshot["is_model_installed_boolean"] = bool(installed)
            console_status = _status_for_prefix(steps, "console_")
        finally:
            client.close()
    else:
        _append_step(steps, "console_config", DIAGNOSTIC_WARNING, "Console URL is not configured", "Configure Console URL for Console API delivery.")

    if vehicle.get("ssh_host") and vehicle.get("ssh_username"):
        ssh_client = ssh_client_factory(
            host=vehicle["ssh_host"],
            port=int(vehicle["ssh_port"]),
            username=vehicle["ssh_username"],
            password=codec.decrypt(vehicle.get("ssh_password_encrypted")),
            private_key_path=vehicle["ssh_private_key_path"],
            host_key_sha256=vehicle.get("ssh_host_key_sha256") or "",
            remote_artifact_root=vehicle["ssh_remote_artifact_root"],
            install_command_template=vehicle["ssh_install_command_template"],
            timeout_seconds=settings.ssh_timeout_seconds,
            retry_count=settings.ssh_retry_count,
            chunk_bytes=settings.ssh_chunk_bytes,
        )
        ssh_result = _capture_step(
            steps,
            "ssh_diagnostics",
            ssh_client.diagnostics,
            "Check SSH credentials, host key, remote permissions, disk space, and model loader service.",
        )
        if isinstance(ssh_result, dict):
            ssh_steps = list(ssh_result.get("steps") or [])
            steps.extend(ssh_steps)
            ssh_snapshot = dict(ssh_result.get("snapshot") or {})
            snapshot.update({f"ssh_{key}": value for key, value in ssh_snapshot.items()})
            rsync_status = "available" if ssh_snapshot.get("rsync_available") else "unavailable"
            if isinstance(ssh_snapshot.get("disk_free_bytes"), int):
                disk_free_bytes = int(ssh_snapshot["disk_free_bytes"])
        ssh_status = _status_for_prefix(steps, "ssh_")
    else:
        _append_step(steps, "ssh_config", DIAGNOSTIC_WARNING, "SSH host or username is not configured", "Configure SSH if fallback delivery is required.")

    overall_status = _overall_status(steps)
    summary = _summary(overall_status, steps)
    diagnostic_id = record_vehicle_diagnostic(
        settings.db_path,
        vehicle_id,
        overall_status=overall_status,
        summary=summary,
        steps=steps,
        snapshot=snapshot,
    )
    record_vehicle_health_check(
        settings.db_path,
        vehicle_id,
        console_status=console_status,
        ssh_status=ssh_status,
        rsync_status=rsync_status,
        disk_free_bytes=disk_free_bytes,
        message=summary,
    )
    return {
        "id": diagnostic_id,
        "vehicle_id": vehicle_id,
        "vehicle_name": vehicle["name"],
        "overall_status": overall_status,
        "summary": summary,
        "steps": steps,
        "snapshot": snapshot,
    }


def _capture_step(steps: list[dict[str, object]], name: str, action: Callable[[], object], suggestion: str) -> object | None:
    started = time.monotonic()
    try:
        result = action()
        _append_step(
            steps,
            name,
            DIAGNOSTIC_READY,
            "ok",
            "",
            duration_seconds=round(time.monotonic() - started, 3),
            output=_safe_output(result),
        )
        return result
    except Exception as exc:  # noqa: BLE001 - diagnostics must capture exact runtime failures.
        _append_step(
            steps,
            name,
            DIAGNOSTIC_ERROR,
            str(exc),
            suggestion,
            duration_seconds=round(time.monotonic() - started, 3),
        )
        return None


def _append_step(
    steps: list[dict[str, object]],
    name: str,
    status: str,
    message: str,
    suggestion: str,
    *,
    duration_seconds: float = 0,
    output: str = "",
) -> None:
    steps.append(
        {
            "name": name,
            "status": status,
            "message": message[:1000],
            "duration_seconds": duration_seconds,
            "output": output[:1000],
            "suggestion": suggestion,
        }
    )


def _safe_output(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    return repr(value)


def _status_for_prefix(steps: list[dict[str, object]], prefix: str) -> str:
    matching = [step for step in steps if str(step.get("name", "")).startswith(prefix)]
    if not matching:
        return "skipped"
    if any(step.get("status") == DIAGNOSTIC_ERROR for step in matching):
        return "failed"
    if any(step.get("status") == DIAGNOSTIC_WARNING for step in matching):
        return "warning"
    return "reachable"


def _overall_status(steps: list[dict[str, object]]) -> str:
    if any(step.get("status") == DIAGNOSTIC_ERROR for step in steps):
        return DIAGNOSTIC_ERROR
    if any(step.get("status") == DIAGNOSTIC_WARNING for step in steps):
        return DIAGNOSTIC_WARNING
    return DIAGNOSTIC_READY


def _summary(overall_status: str, steps: list[dict[str, object]]) -> str:
    errors = [step for step in steps if step.get("status") == DIAGNOSTIC_ERROR]
    warnings = [step for step in steps if step.get("status") == DIAGNOSTIC_WARNING]
    if overall_status == DIAGNOSTIC_ERROR:
        return f"{len(errors)} diagnostic step(s) failed"
    if overall_status == DIAGNOSTIC_WARNING:
        return f"{len(warnings)} diagnostic warning(s)"
    return "All configured vehicle checks passed"
