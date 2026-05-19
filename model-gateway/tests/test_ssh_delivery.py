from __future__ import annotations

from pathlib import Path

import pytest

from model_gateway.ssh_delivery import SshDeliveryClient, SshDeliveryError

from conftest import make_model_tar


class RecordingSshClient(SshDeliveryClient):
    def __init__(self, *args, can_rsync: bool = False, fail_sha: bool = False, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        self.can_rsync = can_rsync
        self.fail_sha = fail_sha
        self.calls: list[str] = []

    def _can_use_rsync(self) -> bool:
        return self.can_rsync

    def _prepare_remote_dir(self, remote_model_dir: str) -> None:
        self.calls.append(f"mkdir:{remote_model_dir}")

    def _upload_with_rsync(self, model_path: Path, remote_model_dir: str) -> None:
        self.calls.append("rsync")

    def _upload_with_sftp(self, model_path: Path, remote_file: str) -> None:
        self.calls.append("sftp")

    def _verify_remote_sha256(self, remote_file: str, local_sha256: str) -> None:
        self.calls.append("sha256")
        if self.fail_sha:
            raise SshDeliveryError("Remote SHA256 does not match local upload")

    def _run_install_command(self, remote_model_dir: str, remote_file: str, folder_name: str, upload_filename: str) -> None:
        self.calls.append(f"install:{folder_name}")

    def _verify_installed(self, remote_model_dir: str) -> None:
        self.calls.append("installed")


def _client(**kwargs) -> RecordingSshClient:  # type: ignore[no-untyped-def]
    return RecordingSshClient(
        host="car.local",
        username="deepracer",
        password="pw",
        retry_count=1,
        **kwargs,
    )


def test_ssh_delivery_prefers_rsync_when_available(tmp_path: Path) -> None:
    archive = make_model_tar(tmp_path / "model.tar.gz")
    client = _client(can_rsync=True)

    result = client.install_model(archive, "model.tar.gz")

    assert result.folder_name == "model"
    assert "rsync" in client.calls
    assert "sftp" not in client.calls
    assert client.calls[-1] == "installed"


def test_ssh_delivery_falls_back_to_sftp(tmp_path: Path) -> None:
    archive = make_model_tar(tmp_path / "model.tar.gz")
    client = _client(can_rsync=False)

    client.install_model(archive, "model.tar.gz")

    assert "sftp" in client.calls
    assert "rsync" not in client.calls


def test_ssh_delivery_fails_on_sha_mismatch(tmp_path: Path) -> None:
    archive = make_model_tar(tmp_path / "model.tar.gz")
    client = _client(fail_sha=True)

    with pytest.raises(SshDeliveryError, match="sha256"):
        client.install_model(archive, "model.tar.gz")


class FakeRemoteFile:
    def __init__(self, sftp: "FakeSftp", path: str) -> None:
        self.sftp = sftp
        self.path = path

    def __enter__(self) -> "FakeRemoteFile":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        pass

    def write(self, chunk: bytes) -> None:
        self.sftp.files[self.path] = self.sftp.files.get(self.path, b"") + chunk


class FakeStat:
    def __init__(self, size: int) -> None:
        self.st_size = size


class FakeSftp:
    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files

    def stat(self, path: str) -> FakeStat:
        if path not in self.files:
            raise OSError(path)
        return FakeStat(len(self.files[path]))

    def remove(self, path: str) -> None:
        self.files.pop(path, None)

    def open(self, path: str, mode: str) -> FakeRemoteFile:
        if "w" in mode:
            self.files[path] = b""
        return FakeRemoteFile(self, path)

    def rename(self, source: str, target: str) -> None:
        self.files[target] = self.files.pop(source)

    def close(self) -> None:
        pass


class FakeSshConnection:
    def __init__(self, sftp: FakeSftp) -> None:
        self.sftp = sftp

    def open_sftp(self) -> FakeSftp:
        return self.sftp

    def close(self) -> None:
        pass


class ResumeSftpClient(SshDeliveryClient):
    def __init__(self, files: dict[str, bytes]) -> None:
        super().__init__(host="car.local", username="deepracer", retry_count=1, chunk_bytes=4)
        self.files = files

    def _connect(self):  # type: ignore[no-untyped-def]
        return FakeSshConnection(FakeSftp(self.files))


def test_sftp_upload_resumes_part_file(tmp_path: Path) -> None:
    model_path = tmp_path / "model.tar.gz"
    model_path.write_bytes(b"abcdef")
    files = {"/remote/model.tar.gz.part": b"abc"}
    client = ResumeSftpClient(files)

    client._upload_with_sftp(model_path, "/remote/model.tar.gz")

    assert files["/remote/model.tar.gz"] == b"abcdef"
    assert "/remote/model.tar.gz.part" not in files
