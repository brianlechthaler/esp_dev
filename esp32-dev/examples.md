# ESP32 Dev Toolkit — Examples

Run all commands after the shared environment is present at `~/.esp32-dev` (or `$ESP32_DEV_PREFIX`).

## Check that the toolkit exists

```bash
test -f "${ESP32_DEV_PREFIX:-$HOME/.esp32-dev}/activate.sh"
python3 -m esp32_dev status --prefix "${ESP32_DEV_PREFIX:-$HOME/.esp32-dev}"
```

## Wrap a single command

From a clone of this repo:

```bash
./esp32-dev/scripts/with-env.sh pio --version
./esp32-dev/scripts/with-env.sh python -m esptool version
./esp32-dev/scripts/with-env.sh idf.py --help
./esp32-dev/scripts/with-env.sh cargo --version
```

After a global Cursor skill install:

```bash
~/.cursor/skills/esp32-dev/scripts/with-env.sh pio run
```

## PlatformIO in a firmware project

```bash
source "$HOME/.esp32-dev/activate.sh"
cd /path/to/firmware
pio run
pio run -t upload --upload-port /dev/ttyUSB0
pio device monitor --port /dev/ttyUSB0 --baud 115200
```

Do not run `pip install platformio` in that project's venv.

## ESP-IDF in a firmware project

```bash
source "$HOME/.esp32-dev/activate.sh"
cd /path/to/idf-app
idf.py set-target esp32
idf.py build
idf.py -p /dev/ttyUSB0 flash monitor
```

Do not clone ESP-IDF next to the app. `IDF_PATH` comes from `activate.sh`.

## Rust

```bash
source "$HOME/.esp32-dev/activate.sh"
esp-generate --headless -o esp32 my-esp-app
cd my-esp-app
cargo build
cargo espflash flash --monitor
```

Do not run `rustup-init` or `cargo install espup` in that project. `CARGO_HOME` and `RUSTUP_HOME` come from `activate.sh`.

## esptool

```bash
source "$HOME/.esp32-dev/activate.sh"
python -m esptool chip_id
python -m esptool --port /dev/ttyUSB0 flash_id
```

## Toolkit missing

Only then, from this repo (once per machine):

```bash
cd /path/to/esp_dev
./scripts/setup-esp32-dev.sh
source "$HOME/.esp32-dev/activate.sh"
```
