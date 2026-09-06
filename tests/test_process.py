"""Tests for SystemHost and CommandRunner."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from esp32_dev.errors import SetupError
from esp32_dev.process import CommandRunner, SystemHost
from tests.conftest import FakeHost


def test_system_host_facts() -> None:
    host = SystemHost()
    assert host.system() == "Linux"
    assert host.python_version() >= (3, 10)
    assert Path(host.python_executable()).exists()
    assert isinstance(host.euid(), int)
    assert isinstance(host.user_gid(), int)
    assert host.username()
    assert host.home().exists()
    assert host.os_release_path() == Path("/etc/os-release")
    assert host.is_root() == (host.euid() == 0)
    assert host.shell()
    root = host.group_members("root")
    assert root is not None
    assert isinstance(root[0], int)
    assert host.group_members("definitely-no-such-group-esp32-dev") is None


def test_system_host_shell_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHELL", "/bin/zsh")
    assert SystemHost().shell() == "/bin/zsh"


def test_system_host_shell_from_passwd(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SHELL", raising=False)

    class Info:
        pw_shell = "/usr/bin/fish"

    monkeypatch.setattr("esp32_dev.process.pwd.getpwuid", lambda _uid: Info())
    assert SystemHost().shell() == "/usr/bin/fish"


@pytest.mark.parametrize("exc", [KeyError("missing"), OSError("denied")])
def test_system_host_shell_fallback(monkeypatch: pytest.MonkeyPatch, exc: Exception) -> None:
    monkeypatch.delenv("SHELL", raising=False)

    def boom(_uid: int) -> None:
        raise exc

    monkeypatch.setattr("esp32_dev.process.pwd.getpwuid", boom)
    assert SystemHost().shell() == "/bin/sh"


def test_run_rejects_empty_command(tmp_path: Path) -> None:
    runner = CommandRunner(FakeHost(tmp_path))
    with pytest.raises(SetupError, match="must not be empty"):
        runner.run([])


def test_which_finds_python() -> None:
    runner = CommandRunner(SystemHost())
    assert runner.which("python3")
    assert runner.which("definitely-no-such-binary-esp32-dev") is None


def test_run_true_and_echo() -> None:
    runner = CommandRunner(SystemHost())
    assert runner.run(["true"]).returncode == 0
    result = runner.run(["echo", "hello"])
    assert "hello" in result.stdout


def test_run_false_check_true() -> None:
    runner = CommandRunner(SystemHost())
    with pytest.raises(SetupError, match="command failed"):
        runner.run(["false"])


def test_run_false_check_false() -> None:
    runner = CommandRunner(SystemHost())
    result = runner.run(["false"], check=False)
    assert result.returncode != 0


def test_run_missing_command() -> None:
    runner = CommandRunner(SystemHost())
    with pytest.raises(SetupError, match="command not found"):
        runner.run(["/no/such/esp32-dev-command"])


def test_run_timeout() -> None:
    runner = CommandRunner(SystemHost())
    with pytest.raises(SetupError, match="timed out"):
        runner.run(["sleep", "5"], timeout=0.05)


def test_dry_run_skips_mutate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CommandRunner(FakeHost(tmp_path), dry_run=True)

    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("subprocess should not run")

    monkeypatch.setattr(subprocess, "run", boom)
    result = runner.run(["apt-get", "install"], mutate=True)
    assert result.returncode == 0


def test_sudo_prefix_when_not_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    host = FakeHost(tmp_path, euid_value=1000)
    runner = CommandRunner(host, use_sudo=True)
    captured: dict[str, Any] = {}

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner.run(["tee", "/tmp/x"], sudo=True, stdin="rules", env={"A": "1"}, cwd=tmp_path)
    assert captured["cmd"][:2] == ["sudo", "tee"]
    assert captured["kwargs"]["input"] == "rules"
    assert captured["kwargs"]["env"] == {"A": "1"}
    assert captured["kwargs"]["cwd"] == tmp_path


def test_sudo_skipped_when_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    host = FakeHost(tmp_path, euid_value=0)
    runner = CommandRunner(host, use_sudo=True)
    captured: dict[str, Any] = {}

    def fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="out", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner.run(["tee", "/tmp/x"], sudo=True)
    assert captured["cmd"][0] == "tee"


def test_sudo_skipped_when_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    host = FakeHost(tmp_path, euid_value=1000)
    runner = CommandRunner(host, use_sudo=False)
    captured: dict[str, Any] = {}

    def fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner.run(["tee", "/tmp/x"], sudo=True)
    assert captured["cmd"][0] == "tee"


def test_none_stdout_stderr_and_empty_failure_detail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = CommandRunner(FakeHost(tmp_path))

    def fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 1, stdout=None, stderr=None)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(SetupError, match="exit 1"):
        runner.run(["false"])


def test_failure_prefers_stderr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CommandRunner(FakeHost(tmp_path))

    def fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 2, stdout="out", stderr="err")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(SetupError, match="err"):
        runner.run(["false"])


def test_failure_uses_stdout_when_stderr_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = CommandRunner(FakeHost(tmp_path))

    def fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 3, stdout="only-out", stderr="  ")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(SetupError, match="only-out"):
        runner.run(["false"])


def test_run_with_real_env_and_cwd(tmp_path: Path) -> None:
    runner = CommandRunner(SystemHost())
    env = dict(os.environ)
    env["ESP32_DEV_TEST"] = "marker"
    result = runner.run(
        ["python3", "-c", "import os; print(os.environ['ESP32_DEV_TEST']); print(os.getcwd())"],
        env=env,
        cwd=tmp_path,
    )
    assert "marker" in result.stdout
    assert str(tmp_path) in result.stdout


def test_run_stdin_cat() -> None:
    runner = CommandRunner(SystemHost())
    result = runner.run(["cat"], stdin="payload\n")
    assert result.stdout == "payload\n"


def test_stream_does_not_capture_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CommandRunner(FakeHost(tmp_path))
    captured: dict[str, object] = {}

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(cmd, 0, stdout=None, stderr=None)

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = runner.run(["true"], stream=True)
    assert result.returncode == 0
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert "capture_output" not in kwargs
