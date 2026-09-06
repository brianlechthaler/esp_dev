# ESP32 development environment

Linux setup for **ESP-IDF**, **PlatformIO**, and **esptool**, including distro packages, a tools virtualenv, udev rules, and `dialout` group membership.

## Quick start

```bash
./scripts/setup-esp32-dev.sh
source ~/.esp32-dev/activate.sh
```

Preview actions without changing the system:

```bash
./scripts/setup-esp32-dev.sh setup --dry-run
```

## Commands

| Command | Purpose |
| --- | --- |
| `setup` | Install selected components (default when the shell wrapper has no args) |
| `resume` | Same as `setup`: drop incomplete leftovers, then continue |
| `status` | Print whether git, cmake, esptool, PlatformIO, ESP-IDF, udev, and dialout are present |
| `verify` | Same as `status`, but exit `1` if required tools are missing |
| `blink` | Verify tools, upload a LED blink sketch, and confirm on/off over serial |

Useful `setup` flags: `--prefix`, `--idf-version`, `--idf-targets esp32,esp32s3`, `--skip-idf`, `--skip-platformio`, `--skip-esptool`, `--skip-packages`, `--no-sudo`, `--force`, `--full-idf-clone`.

By default the installer uses the **latest GitHub release** of ESP-IDF (currently resolved at setup time; pin with `--idf-version v6.1` if you need a specific tag). esptool and PlatformIO are installed with `pip install --upgrade` and no upper-bound pin, so they also track the latest PyPI release.

ESP-IDF is cloned with `--depth 1` and shallow submodules by default so you do not download years of git history. Git progress is printed live. A full-history clone is still available with `--full-idf-clone`.

If you interrupt setup, re-run `./scripts/setup-esp32-dev.sh resume` (or `setup`). Incomplete `esp-idf` trees and `*.partial` staging directories are removed automatically; a complete clone is kept and `install.sh` is run again.

After setup:

- `python -m esptool`
- `pio --help`
- `idf.py --help` (after `source ~/.esp32-dev/activate.sh`)

USB serial access may require logging out and back in after being added to `dialout`.

## Smoke-test

Plug in an ESP32 over USB, then compile and upload a sketch that toggles the onboard LED and prints `LED on` / `LED off` to the serial console every 500 ms:

```bash
./scripts/blink-esp32.sh
```

The script first prints toolchain status (the same check as `verify`), uses esptool to detect the chip (so ESP32-S3 USB-Serial/JTAG boards work without extra flags), flashes with PlatformIO, then reads the serial console until both LED messages appear. The first run may download the `espressif32` platform.

```bash
./scripts/blink-esp32.sh --port /dev/ttyACM0 --pin 48
./scripts/setup-esp32-dev.sh blink --dry-run
```

## Tests and lint

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
make lint
make test
```

CI builds the `test` image and runs the same targets. Locally:

```bash
docker build --target test -t esp32-dev:test .
docker run --rm esp32-dev:test test
docker run --rm esp32-dev:test lint
```

The runtime image (`esp32-dev --help`) is published to GitHub Container Registry on `main` and version tags.
