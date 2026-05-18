# DeepRacer Model Gateway

This service runs on an admin laptop or local server in the same LAN as the AWS DeepRacer cars. Racers upload physical model `.tar.gz` files to the gateway, then an admin reviews the queue and dispatches a selected model to a selected car.

The gateway does not run on the car and does not run on the training stack. It calls the existing DeepRacer vehicle console APIs over the local network.

## Features

- Racer upload page for physical model `.tar.gz` files.
- SQLite queue with upload hashes, model metadata warnings, vehicle records, dispatch records, and audit-friendly timestamps.
- Admin page for approving, rejecting, and dispatching submissions.
- Per-vehicle dispatch lock to prevent concurrent installs to the same car.
- Vehicle adapter for `/api/uploadModels`, `/api/is_model_installed`, and `/api/isModelLoading`.
- No automatic model activation. The MVP installs models only.

## Setup

```powershell
cd model-gateway
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
```

Set a competition admin password before running:

```powershell
$env:GATEWAY_ADMIN_PASSWORD="replace-this"
```

Run the server:

```powershell
python -m uvicorn model_gateway.app:app --host 0.0.0.0 --port 8080
```

Open:

- Racer upload: `http://<gateway-host>:8080/upload`
- Admin console: `http://<gateway-host>:8080/admin`

## Configuration

Environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `GATEWAY_ADMIN_PASSWORD` | `admin` | Admin login password. Change this for events. |
| `GATEWAY_SESSION_SECRET` | `dev-secret-change-me` | HMAC secret for the admin cookie. |
| `GATEWAY_DATA_DIR` | `data` | SQLite database and upload storage directory. |
| `GATEWAY_MAX_UPLOAD_BYTES` | `1073741824` | Max upload size, default 1 GB. |
| `GATEWAY_VEHICLE_TIMEOUT_SECONDS` | `30` | HTTP timeout for vehicle API calls. |
| `GATEWAY_INSTALL_TIMEOUT_SECONDS` | `180` | Max time to wait for model installation. |
| `GATEWAY_INSTALL_POLL_SECONDS` | `3` | Poll interval while waiting for vehicle install. |

## Admin Workflow

1. Add each car in the admin page with its vehicle console URL, for example `http://192.168.0.42`.
2. Racers upload physical model `.tar.gz` files through `/upload`.
3. Admin approves or rejects each submission.
4. Admin selects an approved submission and a vehicle, then dispatches.
5. The gateway uploads the `.tar.gz` to the car as multipart field `file`.
6. The gateway polls the car until the model appears installed or the operation fails.

## Vehicle Assumptions

The target car must be reachable from the gateway host on the same LAN. If a console password is set for the vehicle, store it with the vehicle record so the gateway can create a console session before uploading.

The vehicle-side APIs come from the AWS DeepRacer webserver package:

- `POST /api/uploadModels`
- `GET /api/is_model_installed?filename=<model-folder>`
- `GET /api/isModelLoading`

## Tests

```powershell
python -m pytest tests
```
