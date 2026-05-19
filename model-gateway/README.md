# DeepRacer Model Gateway

This service runs on an admin laptop or local server in the same LAN as the AWS DeepRacer cars. Racers log in, manage teams, and upload physical model `.tar.gz` files. Admins review submissions and dispatch approved models to vehicles.

The gateway does not run on the car or the training stack. The default delivery path uses the existing AWS DeepRacer vehicle console APIs. SSH delivery is an optional fallback for events that need resumable transfer.

## Features

- Separate user and admin login flows.
- SQLite users, sessions, teams, submissions, vehicles, dispatches, and dispatch attempts.
- Admin bootstrap account, user approval, password reset, session revocation, CSV import, and batch user generation.
- User self registration controlled by an admin setting. It is closed by default.
- Hybrid team flow: admins can manage teams, and users can create or join teams by join code.
- Upload validation for `.tar.gz`, max size, SHA256, unsafe tar entries, and `model_metadata.json`.
- Per-vehicle dispatch lock.
- Delivery modes: `auto`, `console_api`, and `ssh`.
- Console API adapter for `/api/uploadModels`, `/api/is_model_installed`, and `/api/isModelLoading`.
- SSH adapter with rsync preference, SFTP resume fallback, retry, keepalive, remote SHA256 verification, and install command execution.
- No automatic model activation. The gateway installs models only.

## Setup

```powershell
cd model-gateway
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
```

Set production secrets before running a competition:

```powershell
$env:GATEWAY_BOOTSTRAP_ADMIN_USERNAME="admin"
$env:GATEWAY_BOOTSTRAP_ADMIN_PASSWORD="replace-this"
$env:GATEWAY_SESSION_SECRET="replace-with-a-long-random-value"
$env:GATEWAY_CREDENTIAL_SECRET="replace-with-a-long-random-value"
```

Run the server:

```powershell
python -m uvicorn model_gateway.app:app --host 0.0.0.0 --port 8080
```

Open:

- User login: `http://<gateway-host>:8080/login`
- Admin login: `http://<gateway-host>:8080/admin/login`

If no admin exists yet, startup creates one from `GATEWAY_BOOTSTRAP_ADMIN_USERNAME` and `GATEWAY_BOOTSTRAP_ADMIN_PASSWORD`. If those variables are not set, development defaults are `admin/admin`; do not use that default in a competition.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `GATEWAY_BOOTSTRAP_ADMIN_USERNAME` | `admin` | Initial admin username when the database has no admin. |
| `GATEWAY_BOOTSTRAP_ADMIN_PASSWORD` | `admin` | Initial admin password. `GATEWAY_ADMIN_PASSWORD` is still accepted as a compatibility fallback. |
| `GATEWAY_SESSION_SECRET` | `dev-secret-change-me` | Secret for session cookie signing and environment separation. |
| `GATEWAY_CREDENTIAL_SECRET` | empty | Encrypts stored vehicle Console and SSH passwords. Empty means development-only encoding. |
| `GATEWAY_DATA_DIR` | `data` | SQLite database and upload storage directory. |
| `GATEWAY_MAX_UPLOAD_BYTES` | `1073741824` | Max upload size, default 1 GB. |
| `GATEWAY_VEHICLE_TIMEOUT_SECONDS` | `30` | HTTP timeout for vehicle Console API calls. |
| `GATEWAY_INSTALL_TIMEOUT_SECONDS` | `180` | Max time to wait for model installation. |
| `GATEWAY_INSTALL_POLL_SECONDS` | `3` | Console API poll interval while waiting for install. |
| `GATEWAY_SSH_TIMEOUT_SECONDS` | `20` | SSH connection and command timeout. |
| `GATEWAY_SSH_RETRY_COUNT` | `3` | SSH transfer/install retry count. |
| `GATEWAY_SSH_CHUNK_BYTES` | `1048576` | SFTP chunk size. |

## Admin Workflow

1. Log in at `/admin/login`.
2. Open `/admin/teams`, set whether user self registration is open, and set the default team size limit.
3. Open `/admin/users` to create admins/users, batch-generate users, import CSV users, approve self-registered users, reset passwords, or revoke sessions.
4. Open `/admin/teams` to create teams, change team limits, and move users between teams.
5. Open `/admin/vehicles` and register each car.
6. Review uploads in `/admin`, approve or reject them, select a vehicle and delivery mode, then dispatch.

Batch CSV format:

```csv
username,display_name,team_name,password
racer001,Ada,Team A,
racer002,Grace,Team A,provided-password
```

When `password` is empty, the gateway generates one and returns a CSV containing the initial passwords. Initial passwords are only shown once.

## User Workflow

1. Log in at `/login`, or register at `/register` if admins opened registration.
2. Create a team or join one by code at `/teams`.
3. Upload a physical DeepRacer model `.tar.gz` at `/upload`.
4. Track submission status on `/dashboard`.

Users must be active and must belong to a team before uploading. A user can belong to one active team at a time in this version.

## Vehicle Delivery

### Console API

Console API delivery is the default. It logs in to the DeepRacer vehicle console when a password is configured, uploads the model as multipart field `file`, and polls install status.

Vehicle endpoints:

- `POST /api/uploadModels`
- `GET /api/is_model_installed?filename=<model-folder>`
- `GET /api/isModelLoading`

### SSH

SSH delivery is optional and requires the vehicle to allow SSH from the gateway host. The SSH user must be able to write below `/opt/aws/deepracer/artifacts` and trigger the ROS2 model loader service.

The target layout is:

```text
/opt/aws/deepracer/artifacts/<model-folder>/<original-filename>.tar.gz
```

The gateway then runs an install command template. The default template calls the existing DeepRacer ROS2 `console_model_action` service. If your vehicle setup uses different ROS2 environment paths, set a custom template in the vehicle form.

Template variables:

- `{artifact_root}`
- `{model_dir}`
- `{model_folder}`
- `{remote_file}`
- `{filename}`

`auto` mode tries Console API first. If Console API fails and SSH is configured, it retries over SSH and records both attempts.

## Tests

```powershell
python -m pytest tests
```

Before pushing changes, run:

```powershell
python -m pytest model-gateway/tests
git diff --check
git status --short --branch
```
