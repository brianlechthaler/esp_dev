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


INSTALL_SCRIPT = REPO / "scripts" / "install.sh"


def test_install_script_is_executable() -> None:
    assert INSTALL_SCRIPT.is_file()
    mode = INSTALL_SCRIPT.stat().st_mode
    assert mode & stat.S_IXUSR


def _fake_python(bin_dir: Path, log: Path) -> None:
    fake_python = bin_dir / "python3"
    fake_python.write_text(
        "#!/usr/bin/env bash\n" + f"printf '%s\\n' \"$@\" > '{log}'\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)


def test_install_script_runs_setup(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "args.txt"
    _fake_python(bin_dir, log)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["HOME"] = str(tmp_path / "home")
    subprocess.run([str(INSTALL_SCRIPT), "--skip-packages"], check=True, env=env, cwd=str(REPO))
    recorded = log.read_text(encoding="utf-8")
    assert "esp32_dev" in recorded
    assert "setup" in recorded
    assert "--skip-packages" in recorded


def test_install_script_sourced_activates_current_shell(tmp_path: Path) -> None:
    home = tmp_path / "home"
    prefix = home / ".esp32-dev"
    prefix.mkdir(parents=True)
    (prefix / "activate.sh").write_text("ESP32_DEV_TEST_MARK=sourced\n", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "args.txt"
    _fake_python(bin_dir, log)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["HOME"] = str(home)
    result = subprocess.run(
        ["bash", "-c", f". '{INSTALL_SCRIPT}' && printf '%s' \"${{ESP32_DEV_TEST_MARK:-}}\""],
        check=True,
        env=env,
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert result.stdout == "sourced"
    recorded = log.read_text(encoding="utf-8")
    assert "setup" in recorded


def test_install_script_sourced_honors_prefix(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    prefix = tmp_path / "custom-prefix"
    prefix.mkdir()
    (prefix / "activate.sh").write_text("ESP32_DEV_TEST_MARK=custom\n", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "args.txt"
    _fake_python(bin_dir, log)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["HOME"] = str(home)
    result = subprocess.run(
        [
            "bash",
            "-c",
            (
                f". '{INSTALL_SCRIPT}' --prefix '{prefix}'"
                f" && printf '%s' \"${{ESP32_DEV_TEST_MARK:-}}\""
            ),
        ],
        check=True,
        env=env,
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert result.stdout == "custom"


def test_install_script_sourced_honors_prefix_equals(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    prefix = tmp_path / "eq-prefix"
    prefix.mkdir()
    (prefix / "activate.sh").write_text("ESP32_DEV_TEST_MARK=equals\n", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "args.txt"
    _fake_python(bin_dir, log)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["HOME"] = str(home)
    result = subprocess.run(
        [
            "bash",
            "-c",
            f". '{INSTALL_SCRIPT}' --prefix={prefix} && printf '%s' \"${{ESP32_DEV_TEST_MARK:-}}\"",
        ],
        check=True,
        env=env,
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert result.stdout == "equals"


def test_install_script_setup_failure_exits_nonzero(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_python = bin_dir / "python3"
    fake_python.write_text("#!/usr/bin/env bash\nexit 7\n", encoding="utf-8")
    fake_python.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["HOME"] = str(tmp_path / "home")
    result = subprocess.run(
        [str(INSTALL_SCRIPT)],
        check=False,
        env=env,
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 7


def test_install_script_sourced_setup_failure_returns(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_python = bin_dir / "python3"
    fake_python.write_text("#!/usr/bin/env bash\nexit 9\n", encoding="utf-8")
    fake_python.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["HOME"] = str(tmp_path / "home")
    result = subprocess.run(
        ["bash", "-c", f". '{INSTALL_SCRIPT}'; printf 'after:%s' \"$?\""],
        check=True,
        env=env,
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert result.stdout == "after:9"
