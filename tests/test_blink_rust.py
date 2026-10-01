"""The Rust blink firmware matches the PlatformIO blink for every supported chip."""

from __future__ import annotations

import re
from pathlib import Path

from esp32_dev.blink import BLINK_INTERVAL_MS, CHIP_TARGETS, LED_OFF_MESSAGE, LED_ON_MESSAGE

ROOT = Path(__file__).resolve().parents[1]
BLINK = ROOT / "firmware" / "blink"
MAIN = (BLINK / "src" / "main.rs").read_text(encoding="utf-8")

# esp-println's USB-SERIAL-JTAG backend exists on these chips. ESP32-S2's native
# USB port is USB-OTG CDC, which esp-println does not implement, and ESP32-C2
# devkits talk over UART. Both still print "LED on" / "LED off" on UART0.
JTAG_SERIAL_CHIPS = frozenset({"ESP32-S3", "ESP32-C3", "ESP32-C5", "ESP32-C6", "ESP32-H2"})
UART_DESPITE_USB_CDC = frozenset({"ESP32-S2", "ESP32-C2"})

# chip -> (crate, cargo feature, rustc target, toolchain channel)
RUST_CHIPS: dict[str, tuple[str, str, str, str]] = {
    "ESP32": ("xtensa", "esp32", "xtensa-esp32-none-elf", "esp"),
    "ESP32-S2": ("xtensa", "esp32s2", "xtensa-esp32s2-none-elf", "esp"),
    "ESP32-S3": ("xtensa", "esp32s3", "xtensa-esp32s3-none-elf", "esp"),
    "ESP32-C2": ("riscv", "esp32c2", "riscv32imc-unknown-none-elf", "stable"),
    "ESP32-C3": ("riscv", "esp32c3", "riscv32imc-unknown-none-elf", "stable"),
    "ESP32-C5": ("riscv", "esp32c5", "riscv32imac-unknown-none-elf", "stable"),
    "ESP32-C6": ("riscv", "esp32c6", "riscv32imac-unknown-none-elf", "stable"),
    "ESP32-H2": ("riscv", "esp32h2", "riscv32imac-unknown-none-elf", "stable"),
}


def _crate(name: str) -> Path:
    return BLINK / name


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _feature_line(cargo: str, feature: str) -> str:
    for line in cargo.splitlines():
        if line.startswith(f"{feature} = "):
            return line
    raise AssertionError(f"missing feature {feature}")


def test_rust_matrix_matches_blink_chips() -> None:
    assert set(RUST_CHIPS) == set(CHIP_TARGETS)
    usb = {chip for chip, target in CHIP_TARGETS.items() if target.usb_cdc}
    assert usb == JTAG_SERIAL_CHIPS | UART_DESPITE_USB_CDC
    assert not JTAG_SERIAL_CHIPS & UART_DESPITE_USB_CDC


def test_blink_messages_and_interval_match() -> None:
    assert f'println!("{LED_ON_MESSAGE}")' in MAIN
    assert f'println!("{LED_OFF_MESSAGE}")' in MAIN
    delays = [int(value) for value in re.findall(r"Duration::from_millis\((\d+)\)", MAIN)]
    assert delays == [BLINK_INTERVAL_MS, BLINK_INTERVAL_MS]
    assert MAIN.index(f'println!("{LED_ON_MESSAGE}")') < MAIN.index("set_low")
    assert MAIN.index("set_high") < MAIN.index(f'println!("{LED_ON_MESSAGE}")')


def test_each_chip_uses_the_blink_pin_and_console() -> None:
    for chip, (crate, feature, triple, channel) in RUST_CHIPS.items():
        target = CHIP_TARGETS[chip]
        pin = re.search(
            rf'#\[cfg\(feature = "{feature}"\)\]\s*let led_pin = peripherals\.GPIO(\d+);',
            MAIN,
        )
        assert pin is not None, feature
        assert int(pin.group(1)) == target.pin

        cargo = _text(_crate(crate) / "Cargo.toml")
        line = _feature_line(cargo, feature)
        interface = "jtag-serial" if chip in JTAG_SERIAL_CHIPS else "uart"
        assert f"esp-hal/{feature}" in line
        assert f"esp-bootloader-esp-idf/{feature}" in line
        assert f"esp-println/{feature}" in line
        assert f"esp-println/{interface}" in line
        if chip in JTAG_SERIAL_CHIPS:
            assert target.usb_cdc is True
        if not target.usb_cdc:
            assert interface == "uart"

        config = _text(_crate(crate) / ".cargo" / "config.toml")
        assert f"[target.{triple}]" in config
        toolchain = _text(_crate(crate) / "rust-toolchain.toml")
        assert f'channel = "{channel}"' in toolchain or f"channel = '{channel}'" in toolchain
        other = "riscv" if crate == "xtensa" else "xtensa"
        assert feature not in _feature_names(_text(_crate(other) / "Cargo.toml"))


def _feature_names(cargo: str) -> set[str]:
    names = set()
    for line in cargo.splitlines():
        if " = [" in line and not line.startswith("["):
            names.add(line.split(" = [", 1)[0].strip())
    return names


def test_default_features_match_the_primary_chips() -> None:
    xtensa = _text(_crate("xtensa") / "Cargo.toml")
    riscv = _text(_crate("riscv") / "Cargo.toml")
    assert 'default = ["esp32"]' in xtensa
    assert 'default = ["esp32c3"]' in riscv
    assert 'target = "xtensa-esp32-none-elf"' in _text(_crate("xtensa") / ".cargo" / "config.toml")
    assert 'target = "riscv32imc-unknown-none-elf"' in _text(
        _crate("riscv") / ".cargo" / "config.toml"
    )
    assert (BLINK / "src" / "main.rs").is_file()
    assert 'path = "../src/main.rs"' in xtensa
    assert 'path = "../src/main.rs"' in riscv


def test_esp_hal_runtime_feature_stays_on() -> None:
    for crate in ("xtensa", "riscv"):
        cargo = _text(_crate(crate) / "Cargo.toml")
        assert 'default-features = false, features = ["rt"]' in cargo


def test_test_image_contains_the_blink_source() -> None:
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    test_stage = text.split("FROM base AS test", 1)[1].split("FROM base AS runtime", 1)[0]
    assert "COPY firmware ./firmware" in test_stage


def test_chip_feature_is_required() -> None:
    assert 'compile_error!("enable exactly one chip feature")' in MAIN
