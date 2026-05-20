from __future__ import annotations

from pathlib import Path
from typing import Callable

from model_gateway.config import Settings
from model_gateway.database import (
    DISPATCH_FAILED,
    DISPATCH_INSTALLED,
    DISPATCH_INSTALLING,
    DISPATCH_MODE_AUTO,
    DISPATCH_MODE_CONSOLE_API,
    DISPATCH_MODE_SSH,
    DISPATCH_UPLOADING,
    DISPATCH_VERIFYING,
    ERROR_CHECKSUM_MISMATCH,
    ERROR_CONSOLE_INSTALL_TIMEOUT,
    ERROR_CONSOLE_LOGIN,
    ERROR_CONSOLE_RESPONSE,
    ERROR_CONSOLE_UPLOAD,
    ERROR_NETWORK,
    ERROR_SSH_AUTH,
    ERROR_SSH_HOST_KEY,
    ERROR_SSH_INSTALL_COMMAND,
    ERROR_SSH_REMOTE_SPACE,
    ERROR_UNKNOWN,
    SUBMISSION_FAILED,
    SUBMISSION_INSTALLED,
    finish_dispatch_attempt,
    get_dispatch_context,
    schedule_dispatch_retry_or_fail,
    start_dispatch_attempt,
    update_dispatch_status,
    update_submission_status,
)
from model_gateway.ssh_delivery import SshDeliveryClient, SshDeliveryError
from model_gateway.vehicle import VehicleClient, VehicleClientError


VehicleClientFactory = Callable[..., VehicleClient]
SshClientFactory = Callable[..., SshDeliveryClient]


def dispatch_model_to_vehicle(
    settings: Settings,
    dispatch_id: int,
    *,
    client_factory: VehicleClientFactory = VehicleClient,
    ssh_client_factory: SshClientFactory = SshDeliveryClient,
) -> None:
    context = get_dispatch_context(settings.db_path, dispatch_id, credential_secret=settings.credential_secret)
    if context is None:
        return

    submission_id = int(context["submission_id"])
    model_path = Path(context["storage_path"])
    modes = _dispatch_modes(context)
    last_error = ""

    for mode in modes:
        attempt_id = start_dispatch_attempt(settings.db_path, dispatch_id, mode, f"Starting {mode} dispatch")
        try:
            if mode == DISPATCH_MODE_CONSOLE_API:
                _dispatch_with_console_api(settings, context, model_path, client_factory=client_factory)
            elif mode == DISPATCH_MODE_SSH:
                _dispatch_with_ssh(settings, context, model_path, ssh_client_factory=ssh_client_factory)
            else:
                raise ValueError(f"Unsupported dispatch mode: {mode}")
            finish_dispatch_attempt(settings.db_path, attempt_id, DISPATCH_INSTALLED, "Dispatch attempt installed model")
            update_dispatch_status(settings.db_path, dispatch_id, DISPATCH_INSTALLED, "Model installed on vehicle")
            update_submission_status(settings.db_path, submission_id, SUBMISSION_INSTALLED)
            return
        except (VehicleClientError, SshDeliveryError, OSError, ValueError) as exc:
            last_error = str(exc)
            finish_dispatch_attempt(settings.db_path, attempt_id, DISPATCH_FAILED, last_error, error_type=_classify_dispatch_error(exc))

    schedule_dispatch_retry_or_fail(
        settings.db_path,
        dispatch_id,
        submission_id,
        last_error or "Dispatch failed",
        max_retries=settings.dispatch_max_retries,
        retry_delay_seconds=settings.dispatch_retry_delay_seconds,
    )


def _dispatch_modes(context: dict[str, object]) -> list[str]:
    requested = str(context.get("requested_mode") or DISPATCH_MODE_AUTO)
    vehicle_default = str(context.get("delivery_mode") or DISPATCH_MODE_AUTO)
    mode = requested if requested != DISPATCH_MODE_AUTO else vehicle_default
    if mode == DISPATCH_MODE_CONSOLE_API:
        return [DISPATCH_MODE_CONSOLE_API]
    if mode == DISPATCH_MODE_SSH:
        return [DISPATCH_MODE_SSH]
    modes = [DISPATCH_MODE_CONSOLE_API]
    if context.get("ssh_host") and context.get("ssh_username"):
        modes.append(DISPATCH_MODE_SSH)
    return modes


def _dispatch_with_console_api(
    settings: Settings,
    context: dict[str, object],
    model_path: Path,
    *,
    client_factory: VehicleClientFactory,
) -> None:
    console_url = str(context.get("console_url") or "")
    if not console_url:
        raise VehicleClientError("Vehicle Console URL is not configured")
    dispatch_id = int(context["dispatch_id"])
    update_dispatch_status(settings.db_path, dispatch_id, DISPATCH_UPLOADING, "Uploading model through Console API")
    with client_factory(
        console_url,
        context.get("console_password"),
        timeout_seconds=settings.vehicle_timeout_seconds,
        install_timeout_seconds=settings.install_timeout_seconds,
        poll_seconds=settings.install_poll_seconds,
    ) as client:
        client.login()
        upload_message = client.upload_model(model_path, str(context["original_filename"]))
        update_dispatch_status(settings.db_path, dispatch_id, DISPATCH_INSTALLING, upload_message)
        folder_name = str(context["original_filename"])[:-7]
        client.wait_until_installed(folder_name)


def _dispatch_with_ssh(
    settings: Settings,
    context: dict[str, object],
    model_path: Path,
    *,
    ssh_client_factory: SshClientFactory,
) -> None:
    dispatch_id = int(context["dispatch_id"])
    update_dispatch_status(settings.db_path, dispatch_id, DISPATCH_UPLOADING, "Uploading model through SSH")
    client = ssh_client_factory(
        host=str(context.get("ssh_host") or ""),
        port=int(context.get("ssh_port") or 22),
        username=str(context.get("ssh_username") or ""),
        password=context.get("ssh_password"),
        private_key_path=str(context.get("ssh_private_key_path") or ""),
        host_key_sha256=str(context.get("ssh_host_key_sha256") or ""),
        remote_artifact_root=str(context.get("ssh_remote_artifact_root") or "/opt/aws/deepracer/artifacts"),
        install_command_template=str(context.get("ssh_install_command_template") or ""),
        timeout_seconds=settings.ssh_timeout_seconds,
        retry_count=settings.ssh_retry_count,
        chunk_bytes=settings.ssh_chunk_bytes,
    )
    result = client.install_model(model_path, str(context["original_filename"]))
    update_dispatch_status(settings.db_path, dispatch_id, DISPATCH_VERIFYING, result.upload_message)


def _classify_dispatch_error(exc: Exception) -> str:
    message = str(exc).lower()
    if isinstance(exc, VehicleClientError):
        if "login" in message:
            return ERROR_CONSOLE_LOGIN
        if "upload" in message or "rejected" in message:
            return ERROR_CONSOLE_UPLOAD
        if "timed out" in message or "timeout" in message:
            return ERROR_CONSOLE_INSTALL_TIMEOUT
        if "json" in message or "response" in message:
            return ERROR_CONSOLE_RESPONSE
        return ERROR_NETWORK
    if isinstance(exc, SshDeliveryError):
        if "authentication" in message or "auth" in message or "permission denied" in message:
            return ERROR_SSH_AUTH
        if "host key" in message or "fingerprint" in message:
            return ERROR_SSH_HOST_KEY
        if "no space" in message or "disk" in message or "space" in message:
            return ERROR_SSH_REMOTE_SPACE
        if "sha256" in message or "checksum" in message:
            return ERROR_CHECKSUM_MISMATCH
        if "install" in message or "console_model_action" in message or "model loader" in message:
            return ERROR_SSH_INSTALL_COMMAND
        return ERROR_NETWORK
    if isinstance(exc, OSError):
        return ERROR_NETWORK
    return ERROR_UNKNOWN
