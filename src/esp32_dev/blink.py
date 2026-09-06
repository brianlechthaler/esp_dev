"""Compile and upload a LED blink sketch to an attached ESP32."""

from __future__ import annotations

import glob
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from esp32_dev.config import SetupConfig
from esp32_dev.errors import SetupError
from esp32_dev.installer import collect_status, format_status, verify_ok
from esp32_dev.process import Host, Runner

logger = logging.getLogger("esp32_dev")

DEFAULT_BOARD = "esp32dev"
DEFAULT_PIN = 2
MAX_PIN = 48
BLINK_INTERVAL_MS = 500
UPLOAD_TIMEOUT_SECONDS = 1800
CONSOLE_TIMEOUT_SECONDS = 8.0
PORT_WAIT_TIMEOUT_SECONDS = 15.0
POST_UPLOAD_PAUSE_SECONDS = 1.0
SERIAL_BAUD = 115200
SERIAL_GLOBS = ("/dev/ttyUSB*", "/dev/ttyACM*")
LED_ON_MESSAGE = "LED on"
LED_OFF_MESSAGE = "LED off"
CHIP_TYPE_RE = re.compile(r"ESP32(?:-[A-Z0-9]+)?")

BLINK_SKETCH = """\
#include <Arduino.h>

#ifndef LED_PIN
#define LED_PIN 2
#endif

void setup() {
  Serial.begin(115200);
  delay(200);
  pinMode(LED_PIN, OUTPUT);
}

void loop() {
  digitalWrite(LED_PIN, HIGH);
  Serial.println("LED on");
  Serial.flush();
  delay(500);
  digitalWrite(LED_PIN, LOW);
  Serial.println("LED off");
  Serial.flush();
  delay(500);
}
"""

PLATFORMIO_INI = """\
[env:esp32]
platform = espressif32
board = {board}
framework = arduino
monitor_speed = 115200
monitor_port = {port}
upload_port = {port}
build_flags =
{build_flags}
"""

CONSOLE_CHECK_CODE = r"""
import sys
import time
import serial

port = sys.argv[1]
baud = int(sys.argv[2])
timeout = float(sys.argv[3])
needle_on = sys.argv[4]
needle_off = sys.argv[5]
ser = serial.Serial()
ser.port = port
ser.baudrate = baud
ser.timeout = 0.5
ser.dtr = False
ser.rts = False
deadline = time.time() + timeout
last_error = None
while time.time() < deadline:
    try:
        if not ser.is_open:
            ser.open()
        break
    except Exception as exc:
        last_error = exc
        time.sleep(0.2)
else:
    raise SystemExit(f"unable to open serial port {port}: {last_error}")
chunks = []
while time.time() < deadline:
    data = ser.read(256)
    if data:
        text = data.decode("utf-8", errors="replace")
        sys.stdout.write(text)
        sys.stdout.flush()
        chunks.append(text)
    joined = "".join(chunks)
    if needle_on in joined and needle_off in joined:
        raise SystemExit(0)
raise SystemExit(1)
"""


@dataclass(frozen=True)
class BlinkTarget:
    """Resolved PlatformIO board, LED pin, and USB-CDC sketch flags."""

    board: str
    pin: int
    usb_cdc: bool
    chip: str


CHIP_TARGETS: dict[str, BlinkTarget] = {
    "ESP32-S3": BlinkTarget("esp32-s3-devkitc-1", 48, True, "ESP32-S3"),
    "ESP32-S2": BlinkTarget("esp32-s2-saola-1", 18, True, "ESP32-S2"),
    "ESP32-C6": BlinkTarget("esp32-c6-devkitc-1", 8, True, "ESP32-C6"),
    "ESP32-C3": BlinkTarget("esp32-c3-devkitm-1", 8, True, "ESP32-C3"),
    "ESP32-H2": BlinkTarget("esp32-h2-devkitm-1", 8, True, "ESP32-H2"),
    "ESP32-C2": BlinkTarget("esp32-c2-devkitm-1", 8, True, "ESP32-C2"),
    "ESP32": BlinkTarget(DEFAULT_BOARD, DEFAULT_PIN, False, "ESP32"),
}


def pause(seconds: float) -> None:
    """Sleep helper so tests can skip post-upload delays."""
    time.sleep(seconds)


def discover_serial_ports() -> list[Path]:
    """Return USB serial device paths that typically belong to ESP32 boards."""
    found: list[Path] = []
    for pattern in SERIAL_GLOBS:
        found.extend(Path(item) for item in sorted(glob.glob(pattern)))
    return found


def resolve_serial_port(requested: str | None) -> str:
    """Return an explicit serial port, or the only attached USB serial device."""
    selected = requested.strip() if requested is not None else ""
    if selected:
        path = Path(selected)
        if not path.exists():
            raise SetupError(f"serial port not found: {selected}")
        return str(path)
    discovered = discover_serial_ports()
    if not discovered:
        raise SetupError(
            "no USB serial device found (expected /dev/ttyUSB* or /dev/ttyACM*). "
            "Plug in an ESP32 and retry, or pass --port."
        )
    if len(discovered) > 1:
        listed = ", ".join(str(item) for item in discovered)
        raise SetupError(f"multiple USB serial devices found: {listed}. Pass --port.")
    return str(discovered[0])


def parse_chip_type(text: str) -> str:
    """Extract an ESP32 chip name from esptool output."""
    matches = CHIP_TYPE_RE.findall(text.upper())
    if not matches:
        raise SetupError(f"unable to parse ESP32 chip type from esptool output:\n{text}")
    return str(max(matches, key=len))


def target_for_chip(chip: str) -> BlinkTarget:
    """Return default board/pin/USB-CDC settings for a detected chip."""
    target = CHIP_TARGETS.get(chip)
    if target is None:
        raise SetupError(f"unsupported ESP32 chip {chip}; pass --board and --pin")
    return target


def validate_pin(pin: int) -> int:
    """Require a GPIO pin in the supported range."""
    if pin < 0 or pin > MAX_PIN:
        raise SetupError(f"invalid GPIO pin: {pin} (expected 0-{MAX_PIN})")
    return pin


def resolve_blink_target(chip: str, board: str | None, pin: int | None) -> BlinkTarget:
    """Apply chip defaults, then optional board and pin overrides."""
    try:
        defaults = target_for_chip(chip)
    except SetupError:
        if board is None or pin is None:
            raise
        resolved_board = board.strip()
        if not resolved_board:
            raise SetupError("board id must not be empty") from None
        return BlinkTarget(resolved_board, validate_pin(pin), True, chip)
    resolved_board = board.strip() if board is not None else defaults.board
    if not resolved_board:
        raise SetupError("board id must not be empty")
    resolved_pin = defaults.pin if pin is None else validate_pin(pin)
    return BlinkTarget(resolved_board, resolved_pin, defaults.usb_cdc, chip)


def detect_chip(runner: Runner, venv_python: Path, port: str) -> str:
    """Ask esptool which ESP32 variant is attached."""
    result = runner.run(
        [str(venv_python), "-m", "esptool", "--port", port, "chip-id"],
        check=False,
        timeout=60,
    )
    text = f"{result.stdout}\n{result.stderr}".strip()
    if result.returncode != 0:
        raise SetupError(f"unable to identify ESP32 on {port}:\n{text}")
    return parse_chip_type(text)


def ensure_blink_ready(config: SetupConfig, runner: Runner, host: Host) -> None:
    """Require a complete ESP32 toolchain before compiling the blink sketch."""
    items = collect_status(config, runner, host)
    print(format_status(items))
    if not verify_ok(items):
        raise SetupError("required tools are missing; run ./scripts/setup-esp32-dev.sh setup")


def blink_project_dir(config: SetupConfig) -> Path:
    """Return the PlatformIO project directory used for the blink sketch."""
    return config.prefix / "projects" / "blink"


def format_build_flags(pin: int, usb_cdc: bool) -> str:
    """Return PlatformIO ``build_flags`` lines for the blink sketch."""
    flags = [f"    -DLED_PIN={pin}"]
    if usb_cdc:
        flags.append("    -DARDUINO_USB_MODE=1")
        flags.append("    -DARDUINO_USB_CDC_ON_BOOT=1")
    return "\n".join(flags)


def write_blink_project(
    project_dir: Path,
    *,
    board: str,
    pin: int,
    port: str,
    usb_cdc: bool,
    dry_run: bool,
) -> None:
    """Write ``platformio.ini`` and the Arduino blink sketch."""
    _write_text(
        project_dir / "platformio.ini",
        PLATFORMIO_INI.format(
            board=board,
            pin=pin,
            port=port,
            build_flags=format_build_flags(pin, usb_cdc),
        ),
        dry_run=dry_run,
    )
    _write_text(project_dir / "src" / "main.cpp", BLINK_SKETCH, dry_run=dry_run)


def blink_console_ok(text: str) -> bool:
    """Return whether serial output includes both LED state messages."""
    return LED_ON_MESSAGE in text and LED_OFF_MESSAGE in text


def wait_for_serial_port(
    port: str,
    *,
    timeout: float = PORT_WAIT_TIMEOUT_SECONDS,
    sleeper: Callable[[float], None] = time.sleep,
    exists: Callable[[Path], bool] | None = None,
) -> None:
    """Wait until ``port`` exists again after a USB re-enumeration."""
    path = Path(port)

    def port_exists(_path: Path) -> bool:
        return path.exists()

    check = exists if exists is not None else port_exists
    deadline = time.monotonic() + timeout
    while True:
        if check(path):
            return
        if time.monotonic() >= deadline:
            raise SetupError(f"serial port disappeared after upload: {port}")
        sleeper(0.2)


def check_blink_console(
    runner: Runner,
    venv_python: Path,
    port: str,
    *,
    timeout: float = CONSOLE_TIMEOUT_SECONDS,
) -> str:
    """Read the serial console until LED on/off messages appear."""
    logger.info("reading serial console on %s", port)
    result = runner.run(
        [
            str(venv_python),
            "-c",
            CONSOLE_CHECK_CODE,
            port,
            str(SERIAL_BAUD),
            str(timeout),
            LED_ON_MESSAGE,
            LED_OFF_MESSAGE,
        ],
        check=False,
        timeout=timeout + 10,
    )
    text = f"{result.stdout}{result.stderr}"
    if result.returncode != 0 or not blink_console_ok(text):
        detail = text.strip() or f"exit {result.returncode}"
        raise SetupError(
            "ESP32 serial console did not report "
            f"{LED_ON_MESSAGE!r} and {LED_OFF_MESSAGE!r}:\n{detail}"
        )
    return text


def run_blink(
    config: SetupConfig,
    runner: Runner,
    host: Host,
    *,
    port: str | None = None,
    board: str | None = None,
    pin: int | None = None,
) -> str:
    """Verify the toolchain, upload a blink sketch, and confirm serial output."""
    if board is not None:
        board = board.strip()
        if not board:
            raise SetupError("board id must not be empty")
    if pin is not None:
        validate_pin(pin)
    ensure_blink_ready(config, runner, host)
    resolved_port = resolve_serial_port(port)
    chip = detect_chip(runner, config.venv_python, resolved_port)
    target = resolve_blink_target(chip, board, pin)
    project_dir = blink_project_dir(config)
    logger.info("writing blink sketch to %s", project_dir)
    write_blink_project(
        project_dir,
        board=target.board,
        pin=target.pin,
        port=resolved_port,
        usb_cdc=target.usb_cdc,
        dry_run=runner.dry_run,
    )
    logger.info(
        "uploading blink sketch to %s (%s, GPIO %s, %sms)",
        resolved_port,
        target.chip,
        target.pin,
        BLINK_INTERVAL_MS,
    )
    runner.run(
        [
            str(config.venv_python),
            "-m",
            "platformio",
            "run",
            "--project-dir",
            str(project_dir),
            "--target",
            "upload",
        ],
        mutate=True,
        stream=True,
        timeout=UPLOAD_TIMEOUT_SECONDS,
    )
    if runner.dry_run:
        print(
            f"Dry run complete; would upload blink sketch to {resolved_port} "
            f"({target.chip}, GPIO {target.pin}) and confirm LED on/off over serial."
        )
        return resolved_port
    wait_for_serial_port(resolved_port)
    pause(POST_UPLOAD_PAUSE_SECONDS)
    console = check_blink_console(runner, config.venv_python, resolved_port)
    print(
        f"Serial console confirmed {LED_ON_MESSAGE!r} and {LED_OFF_MESSAGE!r} on {resolved_port}."
    )
    print(console.strip())
    print(
        f"Uploaded blink sketch to {resolved_port} ({target.chip}, GPIO {target.pin}). "
        "The LED should toggle every 500 ms."
    )
    return resolved_port


def _write_text(path: Path, content: str, *, dry_run: bool) -> None:
    if dry_run:
        logger.info("dry-run: write %s", path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
