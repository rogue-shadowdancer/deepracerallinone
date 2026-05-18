from __future__ import annotations

from pathlib import Path

import httpx

from model_gateway.vehicle import VehicleClient

from conftest import make_model_tar


def test_vehicle_client_uploads_and_polls_install(tmp_path: Path) -> None:
    archive = make_model_tar(tmp_path / "model.tar.gz")
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        if request.url.path == "/login" and request.method == "GET":
            return httpx.Response(200, text='<input name="csrf_token" value="token-1">')
        if request.url.path == "/login" and request.method == "POST":
            return httpx.Response(200, text="ok")
        if request.url.path == "/api/uploadModels":
            assert request.method == "POST"
            assert request.headers.get("x-csrftoken") == "token-1"
            return httpx.Response(200, json={"success": True, "message": "Model uploaded successfully to your vehicle"})
        if request.url.path == "/api/is_model_installed":
            assert request.url.params["filename"] == "model"
            return httpx.Response(200, json={"success": True, "message": "Model is installed"})
        if request.url.path == "/api/isModelLoading":
            return httpx.Response(200, json={"success": True, "isModelLoading": "installing"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    with VehicleClient(
        "http://vehicle.local",
        "password",
        transport=transport,
        install_timeout_seconds=1,
        poll_seconds=0,
    ) as client:
        result = client.install_model(archive, "model.tar.gz")

    assert result.folder_name == "model"
    assert "POST /api/uploadModels" in calls
    assert "GET /api/is_model_installed" in calls
