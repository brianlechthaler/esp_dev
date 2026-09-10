"""Tests for the blink smoke-test."""

from __future__ import annotations

from pathlib import Path

import pytest

from esp32_dev.blink import (
    BLINK_SKETCH,
    DEFAULT_BOARD,
    LED_OFF_MESSAGE,
    LED_ON_MESSAGE,
    MAX_PIN,
    blink_console_ok,
    blink_project_dir,
    check_blink_console,
    detect_chip,
    discover_serial_ports,
    ensure_blink_ready,
    format_build_flags,
    parse_chip_type,
    pause,
    resolve_blink_target,
    resolve_serial_port,
    run_blink,
    target_for_chip,
    validate_pin,
    wait_for_serial_port,
    write_blink_project,
)
from esp32_dev.cli import main
from esp32_dev.config import SetupConfig
from esp32_dev.errors import SetupError
from esp32_dev.process import CommandResult
from tests.conftest import FakeHost, FakeRunner, make_config


def _ready_config(tmp_path: Path) -> tuple[SetupConfig, Path]:
    config = make_config(tmp_path)
    python = config.venv_python
    python.parent.mkdir(parents=True)
    python.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    python.chmod(0o755)
    config.idf_dir.mkdir(parents=True)
    (config.idf_dir / "tools").mkdir()
    (config.idf_dir / "export.sh").write_text("#\n", encoding="utf-8")
    (config.idf_dir / "tools" / "idf.py").write_text("#\n", encoding="utf-8")
    config.cargo_bin.mkdir(parents=True)
    for name in ("rustup", "cargo", "espup"):
        path = config.cargo_bin / name
        path.write_text("#!/bin/sh\n", encoding="utf-8")
        path.chmod(0o755)
    return config, python


def test_discover_serial_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_glob(pattern: str) -> list[str]:
        if pattern == "/dev/ttyUSB*":
            return ["/dev/ttyUSB1", "/dev/ttyUSB0"]
        return ["/dev/ttyACM0"]

    monkeypatch.setattr("esp32_dev.blink.glob.glob", fake_glob)
    assert [str(path) for path in discover_serial_ports()] == [
        "/dev/ttyUSB0",
        "/dev/ttyUSB1",
        "/dev/ttyACM0",
    ]


def test_resolve_serial_port_explicit(tmp_path: Path) -> None:
    port = tmp_path / "ttyUSB0"
    port.write_text("", encoding="utf-8")
    assert resolve_serial_port(f"  {port}  ") == str(port)


def test_resolve_serial_port_missing() -> None:
    with pytest.raises(SetupError, match="serial port not found"):
        resolve_serial_port("/dev/ttyUSB-does-not-exist-esp32-dev")


def test_resolve_serial_port_auto_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "esp32_dev.blink.discover_serial_ports",
        lambda: [Path("/dev/ttyUSB0")],
    )
    assert resolve_serial_port(None) == "/dev/ttyUSB0"
    assert resolve_serial_port("   ") == "/dev/ttyUSB0"


def test_resolve_serial_port_auto_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("esp32_dev.blink.discover_serial_ports", lambda: [])
    with pytest.raises(SetupError, match="no USB serial device found"):
        resolve_serial_port(None)


def test_resolve_serial_port_auto_many(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "esp32_dev.blink.discover_serial_ports",
        lambda: [Path("/dev/ttyUSB0"), Path("/dev/ttyACM0")],
    )
    with pytest.raises(SetupError, match="multiple USB serial devices"):
        resolve_serial_port(None)


def test_parse_chip_type() -> None:
    assert parse_chip_type("Chip type:          ESP32-S3 (QFN56)") == "ESP32-S3"
    assert parse_chip_type("Detecting chip type... ESP32\n") == "ESP32"
    with pytest.raises(SetupError, match="unable to parse ESP32 chip type"):
        parse_chip_type("no chip here")


def test_target_and_resolve_blink_target() -> None:
    classic = target_for_chip("ESP32")
    assert classic.board == DEFAULT_BOARD
    assert classic.usb_cdc is False
    s3 = resolve_blink_target("ESP32-S3", None, None)
    assert s3.board == "esp32-s3-devkitc-1"
    assert s3.pin == 48
    assert s3.usb_cdc is True
    override = resolve_blink_target("ESP32-S3", " custom ", 4)
    assert override.board == "custom"
    assert override.pin == 4
    assert override.usb_cdc is True
    unknown = resolve_blink_target("ESP32-C5", "devkit", 7)
    assert unknown.usb_cdc is True
    assert unknown.board == "devkit"
    with pytest.raises(SetupError, match="unsupported ESP32 chip"):
        target_for_chip("ESP32-C5")
    with pytest.raises(SetupError, match="unsupported ESP32 chip"):
        resolve_blink_target("ESP32-C5", None, 2)
    with pytest.raises(SetupError, match="unsupported ESP32 chip"):
        resolve_blink_target("ESP32-C5", "board", None)
    with pytest.raises(SetupError, match="board id must not be empty"):
        resolve_blink_target("ESP32-C5", "  ", 2)
    with pytest.raises(SetupError, match="board id must not be empty"):
        resolve_blink_target("ESP32", "  ", 2)
    with pytest.raises(SetupError, match="invalid GPIO pin"):
        resolve_blink_target("ESP32-C5", "board", -1)


def test_validate_pin() -> None:
    assert validate_pin(0) == 0
    assert validate_pin(MAX_PIN) == MAX_PIN
    with pytest.raises(SetupError, match="invalid GPIO pin"):
        validate_pin(-1)
    with pytest.raises(SetupError, match="invalid GPIO pin"):
        validate_pin(MAX_PIN + 1)


def test_ensure_blink_ready_missing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = make_config(tmp_path)
    with pytest.raises(SetupError, match="required tools are missing"):
        ensure_blink_ready(config, FakeRunner(), FakeHost(tmp_path))
    assert "esptool" in capsys.readouterr().out


def test_format_build_flags() -> None:
    plain = format_build_flags(2, False)
    assert "-DLED_PIN=2" in plain
    assert "USB_CDC" not in plain
    cdc = format_build_flags(48, True)
    assert "-DLED_PIN=48" in cdc
    assert "ARDUINO_USB_CDC_ON_BOOT" in cdc


def test_write_blink_project(tmp_path: Path) -> None:
    project = tmp_path / "blink"
    write_blink_project(
        project,
        board="esp32dev",
        pin=2,
        port="/dev/ttyUSB0",
        usb_cdc=False,
        dry_run=False,
    )
    ini = (project / "platformio.ini").read_text(encoding="utf-8")
    assert "board = esp32dev" in ini
    assert "upload_port = /dev/ttyUSB0" in ini
    assert "monitor_port = /dev/ttyUSB0" in ini
    assert "-DLED_PIN=2" in ini
    sketch = (project / "src" / "main.cpp").read_text(encoding="utf-8")
    assert sketch == BLINK_SKETCH
    assert LED_ON_MESSAGE in sketch
    assert LED_OFF_MESSAGE in sketch
    write_blink_project(
        project,
        board="esp32-s3-devkitc-1",
        pin=48,
        port="/dev/ttyACM0",
        usb_cdc=True,
        dry_run=False,
    )
    s3_ini = (project / "platformio.ini").read_text(encoding="utf-8")
    assert "ARDUINO_USB_CDC_ON_BOOT" in s3_ini
    dry = tmp_path / "dry"
    write_blink_project(
        dry,
        board="esp32dev",
        pin=2,
        port="/dev/ttyUSB0",
        usb_cdc=False,
        dry_run=True,
    )
    assert not (dry / "platformio.ini").exists()


def test_blink_console_ok() -> None:
    assert blink_console_ok("boot\nLED on\nLED off\n")
    assert not blink_console_ok("LED on\n")
    assert not blink_console_ok("LED off\n")


def test_wait_for_serial_port(tmp_path: Path) -> None:
    port = tmp_path / "ttyUSB0"
    port.write_text("", encoding="utf-8")
    wait_for_serial_port(str(port), timeout=1, sleeper=lambda _seconds: None)
    sleeps: list[float] = []
    states = [False, True]

    def exists(_path: Path) -> bool:
        return states.pop(0) if states else True

    wait_for_serial_port("missing", timeout=5, sleeper=sleeps.append, exists=exists)
    assert sleeps == [0.2]
    with pytest.raises(SetupError, match="disappeared after upload"):
        wait_for_serial_port(
            "missing",
            timeout=0,
            sleeper=lambda _seconds: None,
            exists=lambda _path: False,
        )


def test_detect_chip_success_and_failure(tmp_path: Path) -> None:
    _config, python = _ready_config(tmp_path)
    runner = FakeRunner()
    runner.chip_id_result = CommandResult(0, "Chip type: ESP32-C3\n", "")
    assert detect_chip(runner, python, "/dev/ttyACM0") == "ESP32-C3"
    runner.chip_id_result = CommandResult(1, "", "no device")
    with pytest.raises(SetupError, match="unable to identify ESP32"):
        detect_chip(runner, python, "/dev/ttyACM0")


def test_check_blink_console(tmp_path: Path) -> None:
    python = tmp_path / "python"
    python.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    runner = FakeRunner()
    text = check_blink_console(runner, python, "/dev/ttyUSB0")
    assert blink_console_ok(text)
    runner.console_result = CommandResult(1, "boot noise", "")
    with pytest.raises(SetupError, match="serial console did not report"):
        check_blink_console(runner, python, "/dev/ttyUSB0")
    runner.console_result = CommandResult(0, "LED on\n", "")
    with pytest.raises(SetupError, match="serial console did not report"):
        check_blink_console(runner, python, "/dev/ttyUSB0")
    runner.console_result = CommandResult(1, "  ", "  ")
    with pytest.raises(SetupError, match="exit 1"):
        check_blink_console(runner, python, "/dev/ttyUSB0")


def test_pause(monkeypatch: pytest.MonkeyPatch) -> None:
    slept: list[float] = []
    monkeypatch.setattr("esp32_dev.blink.time.sleep", slept.append)
    pause(0.25)
    assert slept == [0.25]


def test_run_blink_success(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("esp32_dev.blink.pause", lambda _seconds: None)
    config, python = _ready_config(tmp_path)
    port = tmp_path / "ttyUSB0"
    port.write_text("", encoding="utf-8")
    runner = FakeRunner()
    resolved = run_blink(
        config,
        runner,
        FakeHost(tmp_path),
        port=str(port),
        board="esp32dev",
        pin=8,
    )
    assert resolved == str(port)
    project = blink_project_dir(config)
    assert (project / "src" / "main.cpp").is_file()
    assert runner.has_args(str(python), "-m", "platformio", "run")
    assert runner.has_args(str(python), "-m", "esptool")
    out = capsys.readouterr().out
    assert "Uploaded blink sketch" in out
    assert "GPIO 8" in out
    assert "Serial console confirmed" in out
    assert LED_ON_MESSAGE in out


def test_run_blink_auto_s3(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("esp32_dev.blink.pause", lambda _seconds: None)
    config, _python = _ready_config(tmp_path)
    port = tmp_path / "ttyACM0"
    port.write_text("", encoding="utf-8")
    runner = FakeRunner()
    runner.chip_id_result = CommandResult(0, "Chip type:          ESP32-S3 (QFN56)\n", "")
    run_blink(config, runner, FakeHost(tmp_path), port=str(port))
    ini = (blink_project_dir(config) / "platformio.ini").read_text(encoding="utf-8")
    assert "esp32-s3-devkitc-1" in ini
    assert "-DLED_PIN=48" in ini
    assert "ARDUINO_USB_CDC_ON_BOOT" in ini
    assert "ESP32-S3" in capsys.readouterr().out


def test_run_blink_dry_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    config, _python = _ready_config(tmp_path)
    monkeypatch.setattr(
        "esp32_dev.blink.discover_serial_ports",
        lambda: [Path("/dev/ttyACM0")],
    )
    runner = FakeRunner(dry_run=True)
    resolved = run_blink(config, runner, FakeHost(tmp_path))
    assert resolved == "/dev/ttyACM0"
    assert not blink_project_dir(config).exists()
    assert "Dry run complete" in capsys.readouterr().out


def test_run_blink_empty_board(tmp_path: Path) -> None:
    config, _python = _ready_config(tmp_path)
    with pytest.raises(SetupError, match="board id must not be empty"):
        run_blink(config, FakeRunner(), FakeHost(tmp_path), board="  ")


def test_run_blink_unknown_chip_with_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("esp32_dev.blink.pause", lambda _seconds: None)
    config, _python = _ready_config(tmp_path)
    port = tmp_path / "ttyUSB0"
    port.write_text("", encoding="utf-8")
    runner = FakeRunner()
    runner.chip_id_result = CommandResult(0, "Chip type: ESP32-C5\n", "")
    run_blink(
        config,
        runner,
        FakeHost(tmp_path),
        port=str(port),
        board="custom-c5",
        pin=5,
    )
    ini = (blink_project_dir(config) / "platformio.ini").read_text(encoding="utf-8")
    assert "board = custom-c5" in ini
    assert "-DLED_PIN=5" in ini
    assert "ARDUINO_USB_CDC_ON_BOOT" in ini


def test_blink_cli_success(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("esp32_dev.blink.pause", lambda _seconds: None)
    config, _python = _ready_config(tmp_path)
    port = tmp_path / "ttyUSB0"
    port.write_text("", encoding="utf-8")
    code = main(
        [
            "blink",
            "--prefix",
            str(config.prefix),
            "--port",
            str(port),
            "--board",
            "esp32dev",
            "--pin",
            "2",
        ],
        host=FakeHost(tmp_path),
        runner=FakeRunner(),
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "Uploaded blink sketch" in out
    assert "Serial console confirmed" in out


def test_blink_cli_invalid_pin(tmp_path: Path) -> None:
    config, _python = _ready_config(tmp_path)
    code = main(
        ["blink", "--prefix", str(config.prefix), "--pin", "-1"],
        host=FakeHost(tmp_path),
        runner=FakeRunner(),
    )
    assert code == 1


def test_blink_creates_real_runner(tmp_path: Path) -> None:
    code = main(
        ["blink", "--prefix", str(tmp_path), "--dry-run"],
        host=FakeHost(tmp_path),
    )
    assert code == 1
