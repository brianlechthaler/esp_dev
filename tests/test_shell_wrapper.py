"""Tests for the bash setup wrapper."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "setup-esp32-dev.sh"


def test_wrapper_is_executable() -> None:
    assert SCRIPT.is_file()
    mode = SCRIPT.stat().st_mode
    assert mode & stat.S_IXUSR


def test_wrapper_help() -> None:
    result = subprocess.run(
        [str(SCRIPT), "--help"],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )
    assert result.returncode == 0
    assert "ESP-IDF" in result.stdout or "esp32" in result.stdout.lower()


def test_wrapper_no_args_invokes_setup(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "args.txt"
    fake_python = bin_dir / "python3"
    fake_python.write_text(
        "#!/usr/bin/env bash\n" + f"printf '%s\\n' \"$@\" > '{log}'\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    subprocess.run([str(SCRIPT)], check=True, env=env, cwd=str(REPO))
    recorded = log.read_text(encoding="utf-8")
    assert "-m" in recorded
    assert "esp32_dev" in recorded
    assert "setup" in recorded


def test_wrapper_forwards_args(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "args.txt"
    fake_python = bin_dir / "python3"
    fake_python.write_text(
        "#!/usr/bin/env bash\n" + f"printf '%s\\n' \"$@\" > '{log}'\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    subprocess.run([str(SCRIPT), "status", "--prefix", "/tmp"], check=True, env=env, cwd=str(REPO))
    recorded = log.read_text(encoding="utf-8")
    assert "status" in recorded
    assert "--prefix" in recorded


BLINK_SCRIPT = REPO / "scripts" / "blink-esp32.sh"


def test_blink_wrapper_is_executable() -> None:
    assert BLINK_SCRIPT.is_file()
    mode = BLINK_SCRIPT.stat().st_mode
    assert mode & stat.S_IXUSR


def test_blink_wrapper_forwards_args(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "args.txt"
    fake_python = bin_dir / "python3"
    fake_python.write_text(
        "#!/usr/bin/env bash\n" + f"printf '%s\\n' \"$@\" > '{log}'\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    subprocess.run(
        [str(BLINK_SCRIPT), "--port", "/dev/ttyUSB0"],
        check=True,
        env=env,
        cwd=str(REPO),
    )
    recorded = log.read_text(encoding="utf-8")
    assert "esp32_dev" in recorded
    assert "blink" in recorded
    assert "--port" in recorded
    assert "/dev/ttyUSB0" in recorded
