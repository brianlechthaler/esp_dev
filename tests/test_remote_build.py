"""Tests for scripts/remote-build.sh."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "remote-build.sh"
IMAGE = "ghcr.io/brianlechthaler/esp_dev-toolchain:main"


def _fake_ssh(bin_dir: Path, log: Path, code: int = 0) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    ssh = bin_dir / "ssh"
    ssh.write_text(
        "#!/usr/bin/env bash\n" + f"printf '%s\\n' \"$@\" > '{log}'\n" + f"exit {code}\n",
        encoding="utf-8",
    )
    ssh.chmod(0o755)


def _run(tmp_path: Path, args: list[str], *, ssh_code: int = 0) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    log = tmp_path / "ssh.txt"
    _fake_ssh(bin_dir, log, ssh_code)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["HOME"] = str(tmp_path / "local-home")
    return subprocess.run(
        [str(SCRIPT), *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO),
    )


def _ssh_args(tmp_path: Path) -> list[str]:
    return (tmp_path / "ssh.txt").read_text(encoding="utf-8").splitlines()


def _docker_argv(remote_cmd: str, home: str, tmp_path: Path) -> list[str]:
    bin_dir = tmp_path / "docker-bin"
    bin_dir.mkdir()
    log = tmp_path / "docker.txt"
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n" + f"printf '%s\\n' \"$@\" > '{log}'\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["HOME"] = home
    subprocess.run(["bash", "-c", remote_cmd], check=True, env=env, cwd=str(REPO))
    return log.read_text(encoding="utf-8").splitlines()


def test_script_is_executable() -> None:
    assert SCRIPT.is_file()
    assert SCRIPT.stat().st_mode & stat.S_IXUSR


def test_help() -> None:
    result = subprocess.run(
        [str(SCRIPT), "--help"],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )
    assert result.returncode == 0
    assert "--host" in result.stdout
    assert IMAGE in result.stdout
    assert "login shell" in result.stdout


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ([], "--host"),
        (["--host"], "--host"),
        (["--host", "builder"], "--remote"),
        (["--host", "builder", "--remote"], "--remote"),
        (["--host", "builder", "--remote", "builds/espcap", "--"], "command"),
        (["--host", "builder", "--remote", "builds/espcap", "--env"], "--env"),
        (["--host", "builder", "--remote", "builds/espcap", "--env", "MCU"], "KEY=VALUE"),
        (["--host", "builder", "--remote", "builds/espcap", "--image"], "--image"),
        (["--host", "builder", "--remote", "builds/espcap", "--workdir"], "--workdir"),
        (["--bogus"], "unknown"),
    ],
)
def test_rejects_bad_args(tmp_path: Path, args: list[str], message: str) -> None:
    result = _run(tmp_path, args)
    assert result.returncode == 2
    assert message in result.stderr
    assert not (tmp_path / "ssh.txt").exists()


@pytest.mark.parametrize(
    ("remote", "mcu", "target"),
    [
        ("builds/espcap", "esp32s3", "xtensa-esp32s3-espidf"),
        ("~/builds/espcap", "esp32c5", "riscv32imac-esp-espidf"),
        ("$HOME/builds/espcap", "esp32s3", "xtensa-esp32s3-espidf"),
        ("builds/espcap/", "esp32s3", "xtensa-esp32s3-espidf"),
    ],
)
def test_firmware_cargo_build(tmp_path: Path, remote: str, mcu: str, target: str) -> None:
    result = _run(
        tmp_path,
        [
            "--host",
            "100.66.116.123",
            "--remote",
            remote,
            "--workdir",
            "firmware",
            "--env",
            f"MCU={mcu}",
            "--env",
            "IDF_MAINTAINER=1",
            "--",
            "cargo",
            "build",
            "--release",
            "--target",
            target,
        ],
    )
    assert result.returncode == 0, result.stderr
    ssh_args = _ssh_args(tmp_path)
    assert ssh_args[:4] == ["-o", "BatchMode=yes", "--", "100.66.116.123"]
    remote_cmd = ssh_args[4]
    assert '"$HOME/builds/espcap:/workspace"' in remote_cmd
    assert "/tmp" not in remote_cmd
    assert "bash" not in remote_cmd.split()
    argv = _docker_argv(remote_cmd, "/home/builder", tmp_path)
    assert argv[:2] == ["run", "--rm"]
    assert argv[argv.index("-v") + 1] == "/home/builder/builds/espcap:/workspace"
    assert argv[argv.index("-w") + 1] == "/workspace/firmware"
    env_values = [argv[i + 1] for i, arg in enumerate(argv) if arg == "-e"]
    assert env_values == [f"MCU={mcu}", "IDF_MAINTAINER=1"]
    image_at = argv.index(IMAGE)
    assert argv[image_at + 1 :] == ["cargo", "build", "--release", "--target", target]


def test_absolute_remote_and_image_override(tmp_path: Path) -> None:
    image = "ghcr.io/brianlechthaler/esp_dev-toolchain:abc123"
    result = _run(
        tmp_path,
        [
            "--host",
            "builder",
            "--remote",
            "/srv/builds/my tree",
            "--image",
            image,
            "--",
            "idf.py",
            "build",
        ],
    )
    assert result.returncode == 0, result.stderr
    remote_cmd = _ssh_args(tmp_path)[4]
    assert "$HOME" not in remote_cmd
    argv = _docker_argv(remote_cmd, "/home/builder", tmp_path)
    assert argv[argv.index("-v") + 1] == "/srv/builds/my tree:/workspace"
    assert argv[argv.index("-w") + 1] == "/workspace"
    assert argv[argv.index(image) + 1 :] == ["idf.py", "build"]


def test_command_words_with_spaces_stay_intact(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        ["--host", "builder", "--remote", "builds/app", "--", "printf", "hello world"],
    )
    assert result.returncode == 0, result.stderr
    argv = _docker_argv(_ssh_args(tmp_path)[4], "/home/builder", tmp_path)
    assert argv[argv.index(IMAGE) + 1 :] == ["printf", "hello world"]


@pytest.mark.parametrize("remote", ["../secret", "builds/../../etc", "builds/espcap;rm", ""])
def test_rejects_unsafe_remote(tmp_path: Path, remote: str) -> None:
    result = _run(tmp_path, ["--host", "builder", "--remote", remote, "--", "cargo", "build"])
    assert result.returncode == 2
    assert not (tmp_path / "ssh.txt").exists()


def test_ssh_status_propagates(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        ["--host", "builder", "--remote", "builds/espcap", "--", "cargo", "build"],
        ssh_code=3,
    )
    assert result.returncode == 3
