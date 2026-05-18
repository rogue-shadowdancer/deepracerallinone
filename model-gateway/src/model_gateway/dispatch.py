from __future__ import annotations

from pathlib import Path
from typing import Callable

from model_gateway.config import Settings
from model_gateway.database import (
    DISPATCH_FAILED,
    DISPATCH_INSTALLED,
    DISPATCH_INSTALLING,
    DISPATCH_UPLOADING,
    SUBMISSION_FAILED,
    SUBMISSION_INSTALLED,
    get_dispatch_context,
    update_dispatch_status,
    update_submission_status,
)
from model_gateway.vehicle import VehicleClient, VehicleClientError


VehicleClientFactory = Callable[..., VehicleClient]


def dispatch_model_to_vehicle(
    settings: Settings,
    dispatch_id: int,
    *,
    client_factory: VehicleClientFactory = VehicleClient,
) -> None:
    context = get_dispatch_context(settings.db_path, dispatch_id)
    if context is None:
        return

    submission_id = int(context["id"])
    try:
        model_path = Path(context["storage_path"])
        update_dispatch_status(settings.db_path, dispatch_id, DISPATCH_UPLOADING, "Uploading model to vehicle")
        with client_factory(
            context["console_url"],
            context.get("console_password"),
            timeout_seconds=settings.vehicle_timeout_seconds,
            install_timeout_seconds=settings.install_timeout_seconds,
            poll_seconds=settings.install_poll_seconds,
        ) as client:
            client.login()
            upload_message = client.upload_model(model_path, context["original_filename"])
            update_dispatch_status(settings.db_path, dispatch_id, DISPATCH_INSTALLING, upload_message)
            folder_name = context["original_filename"][:-7]
            client.wait_until_installed(folder_name)
        update_dispatch_status(settings.db_path, dispatch_id, DISPATCH_INSTALLED, "Model installed on vehicle")
        update_submission_status(settings.db_path, submission_id, SUBMISSION_INSTALLED)
    except (VehicleClientError, OSError, ValueError) as exc:
        message = str(exc)
        update_dispatch_status(settings.db_path, dispatch_id, DISPATCH_FAILED, message)
        update_submission_status(settings.db_path, submission_id, SUBMISSION_FAILED, message)
