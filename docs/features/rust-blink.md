# Rust blink

`no_std` blink firmware with the same LED pin, serial text, and 500 ms interval as the PlatformIO [blink](blink.md) sketch, for every chip that sketch supports.

## Overview

The source is `firmware/blink/src/main.rs`. It drives the LED high, prints `LED on`, waits 500 ms, drives the LED low, prints `LED off`, and waits 500 ms.

Two crates share that source, because Xtensa and RISC-V use different Rust toolchains:

| Crate | Toolchain | Default chip | Chips |
|-------|-----------|--------------|-------|
| `firmware/blink/xtensa` | `esp` | ESP32, GPIO 2, UART0 | ESP32, ESP32-S2, ESP32-S3 |
| `firmware/blink/riscv` | stable + `rust-src` | ESP32-C3, GPIO 8, USB-SERIAL-JTAG | ESP32-C2, C3, C5, C6, H2 |

`esp-println` `jtag-serial` is the native USB console on ESP32-S3, C3, C5, C6, and H2, matching the PlatformIO `ARDUINO_USB_CDC_ON_BOOT` builds. ESP32 uses UART0. ESP32-S2's native port is USB-OTG CDC, which `esp-println` does not implement, so that chip prints on UART0. ESP32-C2 devkits use UART0 as well.

Pins match the blink chip table: ESP32 GPIO 2, S2 GPIO 18, S3 GPIO 48, C5 GPIO 27, and GPIO 8 on C2, C3, C6, and H2.

## Usage

From a toolchain image (the entrypoint already sourced `activate.sh`):

```bash
# ESP32 (default feature and target)
cargo build --release

# any other chip: one feature, matching target, default features off
cargo build --release --no-default-features --features esp32s3 --target xtensa-esp32s3-none-elf
```

RISC-V crate, from `firmware/blink/riscv`:

```bash
cargo build --release
cargo build --release --no-default-features --features esp32c5 --target riscv32imac-unknown-none-elf
```

| Chip | `--features` | `--target` |
|------|--------------|------------|
| ESP32 | `esp32` | `xtensa-esp32-none-elf` |
| ESP32-S2 | `esp32s2` | `xtensa-esp32s2-none-elf` |
| ESP32-S3 | `esp32s3` | `xtensa-esp32s3-none-elf` |
| ESP32-C2 | `esp32c2` | `riscv32imc-unknown-none-elf` |
| ESP32-C3 | `esp32c3` | `riscv32imc-unknown-none-elf` |
| ESP32-C5 | `esp32c5` | `riscv32imac-unknown-none-elf` |
| ESP32-C6 | `esp32c6` | `riscv32imac-unknown-none-elf` |
| ESP32-H2 | `esp32h2` | `riscv32imac-unknown-none-elf` |

Pass `--no-default-features` whenever you pass `--features`. Otherwise Cargo keeps the default chip feature and the build enables two chips at once.

Remote build with [remote-build.sh](remote-build.md):

```bash
./scripts/remote-build.sh \
  --host HOST \
  --remote builds/esp_dev \
  --workdir firmware/blink/xtensa \
  -- cargo build --release --no-default-features --features esp32s3 --target xtensa-esp32s3-none-elf
```

## On-device status

ESP32-S3 and ESP32-C5 are the only chips that have been flashed and checked for `LED on` and `LED off`. ESP32, ESP32-S2, ESP32-C2, ESP32-C3, ESP32-C6, and ESP32-H2 remain untested on hardware, as do the ESP32-only ESP-IDF and PlatformIO smoke projects.

## Related

- [Blink](blink.md)
- [Rust](rust.md)
- [Remote build](remote-build.md)
