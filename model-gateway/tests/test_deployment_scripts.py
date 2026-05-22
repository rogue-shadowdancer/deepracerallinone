from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


PROJECT_DIR = Path(__file__).resolve().parents[1]


def _powershell() -> str | None:
    return shutil.which("pwsh") or shutil.which("powershell")


def _powershell_command(script: Path, *args: str) -> list[str]:
    executable = _powershell()
    if executable is None:
        pytest.skip("PowerShell is not available")
    command = [executable, "-NoProfile"]
    if Path(executable).name.lower().startswith("powershell"):
        command.extend(["-ExecutionPolicy", "Bypass"])
    command.extend(["-File", str(script), *args])
    return command


def test_windows_deploy_dry_run_competition_and_dev() -> None:
    script = PROJECT_DIR / "scripts" / "deploy-windows.ps1"
    competition = subprocess.run(
        _powershell_command(script, "-DryRun"),
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Mode: competition" in competition.stdout
    assert ".gateway.env" in competition.stdout
    assert "admin/admin" not in competition.stdout

    dev = subprocess.run(
        _powershell_command(script, "-Mode", "dev", "-DryRun"),
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Mode: dev" in dev.stdout


def test_windows_run_dry_run_loads_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".gateway.env"
    data_dir = tmp_path / "gateway-data"
    env_file.write_text(f"GATEWAY_DATA_DIR={data_dir}\nGATEWAY_COMPETITION_MODE=false\n", encoding="utf-8")

    result = subprocess.run(
        _powershell_command(PROJECT_DIR / "scripts" / "run-windows.ps1", "-EnvFile", str(env_file), "-Port", "9090", "-DryRun"),
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        check=True,
    )

    assert str(data_dir) in result.stdout
    assert "http://0.0.0.0:9090/admin/login" in result.stdout


def test_linux_scripts_syntax_and_dry_run(tmp_path: Path) -> None:
    bash = shutil.which("bash")
    python3 = shutil.which("python3")
    if bash is None:
        pytest.skip("bash is not available")

    scripts = [PROJECT_DIR / "scripts" / "run-linux.sh", PROJECT_DIR / "scripts" / "deploy-linux.sh"]
    subprocess.run([bash, "-n", *(str(script) for script in scripts)], cwd=PROJECT_DIR, check=True)

    if python3 is None:
        pytest.skip("python3 is not available for deploy-linux secret generation")

    env = {**os.environ, "PATH": os.environ.get("PATH", "")}
    competition = subprocess.run(
        [
            bash,
            str(PROJECT_DIR / "scripts" / "deploy-linux.sh"),
            "--mode",
            "competition",
            "--allow-insecure-lan-cookie",
            "--data-dir",
            str(tmp_path / "data"),
            "--dry-run",
        ],
        cwd=PROJECT_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Mode: competition" in competition.stdout
    assert "admin/admin" not in competition.stdout

    dev = subprocess.run(
        [bash, str(PROJECT_DIR / "scripts" / "deploy-linux.sh"), "--mode", "dev", "--dry-run"],
        cwd=PROJECT_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Mode: dev" in dev.stdout


def test_gitignore_covers_local_deployment_artifacts() -> None:
    gitignore = (PROJECT_DIR / ".gitignore").read_text(encoding="utf-8")

    for pattern in [".gateway.env", ".venv/", "data/", "backups/", "*.log"]:
        assert pattern in gitignore
