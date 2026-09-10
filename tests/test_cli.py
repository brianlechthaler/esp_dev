"""Tests for the CLI."""

from __future__ import annotations

import logging
import sys
from argparse import Namespace
from pathlib import Path

import pytest

from esp32_dev.cli import (
    _dispatch,
    build_parser,
    config_from_args,
    configure_logging,
    console_entry,
    main,
    parse_idf_targets,
    prefix_from_args,
)
from esp32_dev.errors import SetupError
from tests.conftest import FakeHost, FakeRunner


def test_parse_idf_targets() -> None:
    assert parse_idf_targets("esp32, esp32s3,,") == ("esp32", "esp32s3")
    assert parse_idf_targets("  ") == ()


def test_help_and_version() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as help_exc:
        parser.parse_args(["--help"])
    assert help_exc.value.code == 0
    with pytest.raises(SystemExit) as version_exc:
        parser.parse_args(["--version"])
    assert version_exc.value.code == 0


def test_no_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    captured = capsys.readouterr()
    assert "setup" in captured.out
    assert "blink" in captured.out


def test_quiet_and_verbose_conflict() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["-q", "-v", "status"])
    assert exc.value.code == 2


def test_configure_logging_levels() -> None:
    configure_logging(verbose=False, quiet=True)
    assert logging.getLogger("esp32_dev").level == logging.ERROR
    configure_logging(verbose=True, quiet=False)
    assert logging.getLogger("esp32_dev").level == logging.DEBUG
    configure_logging(verbose=False, quiet=False)
    assert logging.getLogger("esp32_dev").level == logging.INFO


def test_config_from_args(tmp_path: Path) -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "setup",
            "--prefix",
            str(tmp_path / "env"),
            "--idf-version",
            "v6.1",
            "--idf-targets",
            "esp32,esp32s3",
            "--skip-packages",
            "--no-sudo",
            "--dry-run",
            "--force",
            "--full-idf-clone",
        ]
    )
    config = config_from_args(args)
    assert config.prefix == (tmp_path / "env").resolve()
    assert config.idf_targets == ("esp32", "esp32s3")
    assert config.skip_packages is True
    assert config.use_sudo is False
    assert config.dry_run is True
    assert config.force is True
    assert config.shallow_idf is False
    assert config.idf_version == "v6.1"
    assert config.skip_shell is False
    assert config.skip_rust is False


def test_prefix_from_args(tmp_path: Path) -> None:
    args = Namespace(prefix=str(tmp_path))
    assert prefix_from_args(args) == tmp_path.resolve()


def test_config_from_args_default_is_shallow(tmp_path: Path) -> None:
    parser = build_parser()
    args = parser.parse_args(["setup", "--prefix", str(tmp_path)])
    assert config_from_args(args).shallow_idf is True
    assert config_from_args(args).idf_version == "latest"


def test_config_from_args_skip_shell(tmp_path: Path) -> None:
    parser = build_parser()
    args = parser.parse_args(["setup", "--prefix", str(tmp_path), "--skip-shell"])
    assert config_from_args(args).skip_shell is True


def test_config_from_args_skip_rust(tmp_path: Path) -> None:
    parser = build_parser()
    args = parser.parse_args(["setup", "--prefix", str(tmp_path), "--skip-rust"])
    assert config_from_args(args).skip_rust is True


def test_setup_success(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("esp32_dev.releases.fetch_latest_idf_release_tag", lambda: "v6.1")
    host = FakeHost(tmp_path)
    runner = FakeRunner()
    code = main(
        [
            "setup",
            "--prefix",
            str(tmp_path / "prefix"),
            "--skip-packages",
            "--skip-udev",
            "--skip-dialout",
            "--idf-targets",
            "esp32",
        ],
        host=host,
        runner=runner,
    )
    assert code == 0
    assert runner.has_args("git", "clone", "--progress", "--branch", "v6.1")
    captured = capsys.readouterr()
    assert "ESP32 development environment is ready" in captured.out


def test_resume_success(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("esp32_dev.releases.fetch_latest_idf_release_tag", lambda: "v6.1")
    host = FakeHost(tmp_path)
    runner = FakeRunner()
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    leftover = prefix / "esp-idf.partial"
    leftover.mkdir()
    (leftover / "junk").write_text("x", encoding="utf-8")
    code = main(
        [
            "resume",
            "--prefix",
            str(prefix),
            "--skip-packages",
            "--skip-udev",
            "--skip-dialout",
        ],
        host=host,
        runner=runner,
    )
    assert code == 0
    assert not leftover.exists()
    assert "ESP32 development environment is ready" in capsys.readouterr().out


def test_setup_error_returns_one(tmp_path: Path) -> None:
    host = FakeHost(tmp_path, system_name="Windows")
    code = main(
        ["setup", "--prefix", str(tmp_path), "--skip-packages"],
        host=host,
        runner=FakeRunner(),
    )
    assert code == 1


def test_setup_empty_targets_returns_one(tmp_path: Path) -> None:
    code = main(
        ["setup", "--prefix", str(tmp_path), "--idf-targets", " , "],
        host=FakeHost(tmp_path),
        runner=FakeRunner(),
    )
    assert code == 1


def test_status_and_verify(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    host = FakeHost(tmp_path)
    runner = FakeRunner()
    prefix = tmp_path / "prefix"
    assert main(["status", "--prefix", str(prefix)], host=host, runner=runner) == 0
    out = capsys.readouterr().out
    assert "esptool" in out
    assert "rustup" in out
    assert main(["verify", "--prefix", str(prefix)], host=host, runner=runner) == 1


def test_unknown_command(tmp_path: Path) -> None:
    args = Namespace(command="nope", prefix=str(tmp_path), verbose=False, quiet=False)
    with pytest.raises(SetupError, match="unknown command"):
        _dispatch(args, FakeHost(tmp_path), FakeRunner())


def test_console_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("esp32_dev.cli.main", lambda argv=None: 3)
    with pytest.raises(SystemExit) as exc:
        console_entry()
    assert exc.value.code == 3


def test_main_uses_sys_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["esp32-dev"])
    assert main() == 0


def test_status_creates_real_runner(tmp_path: Path) -> None:
    code = main(["status", "--prefix", str(tmp_path)], host=FakeHost(tmp_path))
    assert code == 0


def test_setup_creates_real_runner_dry_run(tmp_path: Path) -> None:
    code = main(
        [
            "-q",
            "setup",
            "--dry-run",
            "--no-sudo",
            "--skip-packages",
            "--skip-esptool",
            "--skip-platformio",
            "--skip-idf",
            "--skip-rust",
            "--skip-udev",
            "--skip-dialout",
            "--prefix",
            str(tmp_path / "prefix"),
        ],
        host=FakeHost(tmp_path),
    )
    assert code == 0


def test_verbose_setup(tmp_path: Path) -> None:
    code = main(
        [
            "-v",
            "setup",
            "--dry-run",
            "--skip-packages",
            "--skip-esptool",
            "--skip-platformio",
            "--skip-idf",
            "--skip-rust",
            "--skip-udev",
            "--skip-dialout",
            "--prefix",
            str(tmp_path / "prefix"),
        ],
        host=FakeHost(tmp_path),
        runner=FakeRunner(dry_run=True),
    )
    assert code == 0
