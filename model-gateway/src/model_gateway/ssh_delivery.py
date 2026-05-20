from __future__ import annotations

import hashlib
import base64
import os
import posixpath
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from model_gateway.storage import model_folder_name


class SshDeliveryError(RuntimeError):
    """Raised when an SSH model install cannot complete."""


@dataclass(frozen=True)
class SshInstallResult:
    folder_name: str
    upload_message: str


DEFAULT_INSTALL_COMMAND_TEMPLATE = (
    "bash -lc '"
    "source /opt/ros/foxy/setup.bash; "
    "if [ -f /opt/aws/deepracer/setup.bash ]; then source /opt/aws/deepracer/setup.bash; fi; "
    "ros2 service call /deepracer_systems_pkg/console_model_action "
    "deepracer_interfaces_pkg/srv/ConsoleModelActionSrv "
    "\"{model_path: \\\"{model_dir}\\\", action: 1}\"'"
)


class SshDeliveryClient:
    def __init__(
        self,
        *,
        host: str,
        port: int = 22,
        username: str,
        password: str | None = None,
        private_key_path: str | None = None,
        host_key_sha256: str = "",
        remote_artifact_root: str = "/opt/aws/deepracer/artifacts",
        install_command_template: str = "",
        timeout_seconds: int = 20,
        retry_count: int = 3,
        chunk_bytes: int = 1024 * 1024,
        sleeper: Callable[[float], None] = time.sleep,
        prefer_rsync: bool = True,
    ) -> None:
        self.host = host
        self.port = int(port or 22)
        self.username = username
        self.password = password
        self.private_key_path = private_key_path or ""
        self.host_key_sha256 = _normalize_fingerprint(host_key_sha256)
        self.remote_artifact_root = remote_artifact_root.rstrip("/") or "/opt/aws/deepracer/artifacts"
        self.install_command_template = install_command_template or DEFAULT_INSTALL_COMMAND_TEMPLATE
        self.timeout_seconds = timeout_seconds
        self.retry_count = max(1, retry_count)
        self.chunk_bytes = max(64 * 1024, chunk_bytes)
        self.sleeper = sleeper
        self.prefer_rsync = prefer_rsync

    def install_model(self, model_path: Path, upload_filename: str) -> SshInstallResult:
        if not model_path.is_file():
            raise SshDeliveryError(f"Model file not found: {model_path}")
        if not self.host or not self.username:
            raise SshDeliveryError("SSH host and username are required")

        folder_name = model_folder_name(upload_filename)
        remote_model_dir = posixpath.join(self.remote_artifact_root, folder_name)
        remote_file = posixpath.join(remote_model_dir, upload_filename)
        local_sha256 = _sha256_file(model_path)

        self._with_retries(lambda: self._prepare_remote_dir(remote_model_dir), "prepare remote model directory")
        if self.prefer_rsync and self._can_use_rsync():
            self._with_retries(lambda: self._upload_with_rsync(model_path, remote_model_dir), "rsync model")
        else:
            self._with_retries(lambda: self._upload_with_sftp(model_path, remote_file), "sftp model")
        self._with_retries(lambda: self._verify_remote_sha256(remote_file, local_sha256), "verify remote sha256")
        self._with_retries(lambda: self._run_install_command(remote_model_dir, remote_file, folder_name, upload_filename), "install model")
        self._with_retries(lambda: self._verify_installed(remote_model_dir), "verify model install")
        return SshInstallResult(folder_name=folder_name, upload_message="Model installed over SSH")

    def _with_retries(self, action: Callable[[], None], label: str) -> None:
        last_error: Exception | None = None
        for attempt in range(1, self.retry_count + 1):
            try:
                action()
                return
            except Exception as exc:  # noqa: BLE001 - keep retries generic around network calls.
                last_error = exc
                if attempt >= self.retry_count:
                    break
                self.sleeper(min(2 ** attempt, 8))
        raise SshDeliveryError(f"SSH {label} failed: {last_error}") from last_error

    def _can_use_rsync(self) -> bool:
        return bool(shutil.which("rsync") and self.private_key_path)

    def _upload_with_rsync(self, model_path: Path, remote_model_dir: str) -> None:
        remote_target = f"{self.username}@{self.host}:{_shell_quote(remote_model_dir)}/"
        ssh_cmd = f"ssh -p {self.port} -o ServerAliveInterval=10 -o ServerAliveCountMax=3"
        if self.private_key_path:
            ssh_cmd += f" -i {_shell_quote(self.private_key_path)}"
        command = [
            "rsync",
            "--partial",
            "--compress",
            "--inplace",
            "-e",
            ssh_cmd,
            str(model_path),
            remote_target,
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=self.timeout_seconds * 60)
        if result.returncode != 0:
            raise SshDeliveryError(result.stderr.strip() or "rsync failed")

    def _upload_with_sftp(self, model_path: Path, remote_file: str) -> None:
        part_file = remote_file + ".part"
        client = self._connect()
        try:
            sftp = client.open_sftp()
            try:
                remote_size = self._remote_size(sftp, part_file)
                local_size = os.path.getsize(model_path)
                if remote_size > local_size:
                    sftp.remove(part_file)
                    remote_size = 0
                mode = "ab" if remote_size else "wb"
                with model_path.open("rb") as local_file:
                    local_file.seek(remote_size)
                    with sftp.open(part_file, mode) as remote:
                        while True:
                            chunk = local_file.read(self.chunk_bytes)
                            if not chunk:
                                break
                            remote.write(chunk)
                sftp.rename(part_file, remote_file)
            finally:
                sftp.close()
        finally:
            client.close()

    def _prepare_remote_dir(self, remote_model_dir: str) -> None:
        self._exec(f"mkdir -p {_shell_quote(remote_model_dir)}")

    def _verify_remote_sha256(self, remote_file: str, local_sha256: str) -> None:
        output = self._exec(f"sha256sum {_shell_quote(remote_file)}")
        remote_sha256 = output.strip().split()[0] if output.strip() else ""
        if remote_sha256 != local_sha256:
            raise SshDeliveryError("Remote SHA256 does not match local upload")

    def _run_install_command(self, remote_model_dir: str, remote_file: str, folder_name: str, upload_filename: str) -> None:
        command = self.install_command_template.format(
            artifact_root=self.remote_artifact_root,
            model_dir=remote_model_dir,
            model_folder=folder_name,
            remote_file=remote_file,
            filename=upload_filename,
        )
        self._exec(command)

    def _verify_installed(self, remote_model_dir: str) -> None:
        self._exec(f"test -s {_shell_quote(posixpath.join(remote_model_dir, 'checksum.txt'))}")

    def preflight(self) -> dict[str, object]:
        diagnostics = self.diagnostics()
        failed = [step for step in diagnostics["steps"] if step["status"] == "error"]
        if failed:
            raise SshDeliveryError("; ".join(str(step["message"]) for step in failed))
        rsync_status = "available" if diagnostics["snapshot"].get("rsync_available") else "unavailable"
        disk_free_bytes = diagnostics["snapshot"].get("disk_free_bytes")
        if not isinstance(disk_free_bytes, int):
            disk_free_bytes = None
        return {"ssh_status": "reachable", "rsync_status": rsync_status, "disk_free_bytes": disk_free_bytes}

    def diagnostics(self) -> dict[str, object]:
        steps: list[dict[str, object]] = []
        snapshot: dict[str, object] = {
            "host_key_configured": bool(self.host_key_sha256),
            "rsync_available": bool(self._can_use_rsync()),
            "remote_artifact_root": self.remote_artifact_root,
        }

        def run_step(name: str, command: str, suggestion: str = "") -> str:
            started = time.monotonic()
            try:
                output = self._exec(command)
                steps.append(
                    {
                        "name": name,
                        "status": "ready",
                        "message": "ok",
                        "duration_seconds": round(time.monotonic() - started, 3),
                        "output": output.strip()[:1000],
                        "suggestion": "",
                    }
                )
                return output
            except Exception as exc:  # noqa: BLE001 - diagnostics should capture exact field failures.
                steps.append(
                    {
                        "name": name,
                        "status": "error",
                        "message": str(exc),
                        "duration_seconds": round(time.monotonic() - started, 3),
                        "output": "",
                        "suggestion": suggestion,
                    }
                )
                return ""

        run_step("ssh_connect", "true", "Check SSH host, port, username, password/key, and host key fingerprint.")
        run_step(
            "remote_artifact_root_writable",
            f"mkdir -p {_shell_quote(self.remote_artifact_root)} && test -w {_shell_quote(self.remote_artifact_root)}",
            "Grant the SSH user write access to the DeepRacer artifact root or choose a writable root.",
        )
        disk_output = run_step(
            "remote_disk_space",
            f"df -Pk {_shell_quote(self.remote_artifact_root)} | tail -1 | awk '{{print $4}}'",
            "Free space on the vehicle before dispatching large physical model archives.",
        )
        try:
            snapshot["disk_free_bytes"] = int(disk_output.strip()) * 1024
        except ValueError:
            snapshot["disk_free_bytes"] = None
        if snapshot["rsync_available"]:
            steps.append(
                {
                    "name": "rsync_local",
                    "status": "ready",
                    "message": "local rsync and SSH private key are configured",
                    "duration_seconds": 0,
                    "output": "",
                    "suggestion": "",
                }
            )
        else:
            steps.append(
                {
                    "name": "rsync_local",
                    "status": "warning",
                    "message": "rsync acceleration unavailable; SFTP resume fallback will be used",
                    "duration_seconds": 0,
                    "output": "",
                    "suggestion": "Install rsync locally and use SSH key auth if faster transfer is needed.",
                }
            )
        run_step(
            "model_loader_service",
            "bash -lc 'source /opt/ros/foxy/setup.bash >/dev/null 2>&1; "
            "if [ -f /opt/aws/deepracer/setup.bash ]; then source /opt/aws/deepracer/setup.bash >/dev/null 2>&1; fi; "
            "ros2 service list 2>/dev/null | grep -q /deepracer_systems_pkg/console_model_action'",
            "Confirm ROS2 Foxy and the DeepRacer model loader service are running on the vehicle.",
        )
        return {"steps": steps, "snapshot": snapshot}

    def _exec(self, command: str) -> str:
        client = self._connect()
        try:
            _, stdout, stderr = client.exec_command(command, timeout=self.timeout_seconds)
            exit_status = stdout.channel.recv_exit_status()
            stdout_text = stdout.read().decode("utf-8", errors="replace")
            stderr_text = stderr.read().decode("utf-8", errors="replace")
            if exit_status != 0:
                raise SshDeliveryError(stderr_text.strip() or stdout_text.strip() or f"Command failed: {command}")
            return stdout_text
        finally:
            client.close()

    def _connect(self):  # type: ignore[no-untyped-def]
        try:
            import paramiko
        except ImportError as exc:
            raise SshDeliveryError("paramiko is required for SSH delivery") from exc

        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(_FingerprintPolicy(self.host_key_sha256))
        connect_kwargs: dict[str, object] = {
            "hostname": self.host,
            "port": self.port,
            "username": self.username,
            "timeout": self.timeout_seconds,
            "banner_timeout": self.timeout_seconds,
            "auth_timeout": self.timeout_seconds,
        }
        if self.private_key_path:
            connect_kwargs["key_filename"] = self.private_key_path
        if self.password:
            connect_kwargs["password"] = self.password
        client.connect(**connect_kwargs)
        transport = client.get_transport()
        if transport is not None:
            if self.host_key_sha256:
                remote_key = transport.get_remote_server_key()
                if _key_sha256(remote_key) != self.host_key_sha256:
                    client.close()
                    raise SshDeliveryError("SSH host key fingerprint does not match configured value")
            transport.set_keepalive(10)
        return client

    @staticmethod
    def _remote_size(sftp, remote_path: str) -> int:  # type: ignore[no-untyped-def]
        try:
            return int(sftp.stat(remote_path).st_size)
        except OSError:
            return 0


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def _normalize_fingerprint(value: str) -> str:
    value = value.strip()
    if value.startswith("SHA256:"):
        value = value[len("SHA256:"):]
    return value


def _key_sha256(key) -> str:  # type: ignore[no-untyped-def]
    return base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode("ascii").rstrip("=")


class _FingerprintPolicy:
    def __init__(self, expected_sha256: str = "") -> None:
        self.expected_sha256 = expected_sha256

    def missing_host_key(self, client, hostname, key) -> None:  # type: ignore[no-untyped-def]
        actual = _key_sha256(key)
        if self.expected_sha256 and actual != self.expected_sha256:
            raise SshDeliveryError("SSH host key fingerprint does not match configured value")
        if not self.expected_sha256:
            # Accept for local competition LANs without persisting unknown host keys.
            return
