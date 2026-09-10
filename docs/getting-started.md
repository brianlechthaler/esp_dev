# Getting started

Install ESP-IDF, PlatformIO, esptool, and the Espressif Rust toolchain on Linux, then activate them in the current shell.

## Requirements

| Need | Detail |
|------|--------|
| OS | Linux only |
| Distro | Debian/Ubuntu (and derivatives), Fedora/RHEL-family, or Arch-family |
| Python | 3.10 or newer on the host |
| Privileges | sudo for distro packages, udev rules, and `dialout` (or pass `--no-sudo` / skip those steps) |
| Network | GitHub (ESP-IDF, rustup, espup) and PyPI |

Unsupported distros: install the Debian package list yourself and re-run with `--skip-packages`. See [Setup](features/setup.md).

## Install the toolkit

From a clone of this repo:

```bash
. ./scripts/install.sh
```

That runs `setup`, hooks **bash**, **zsh**, **fish**, **ksh**, and POSIX **sh** so new interactive shells activate the prefix, and (when sourced) activates the current bash or zsh session. Running without sourcing still hooks future shells:

```bash
./scripts/install.sh
./scripts/install.sh --dry-run
```

The older wrapper `./scripts/setup-esp32-dev.sh` with no arguments also runs `setup`. Extra arguments are passed to `python3 -m esp32_dev` (the wrapper sets `PYTHONPATH`). After that wrapper, activate this shell yourself: `source ~/.esp32-dev/activate.sh`.

After `pip install .` or `pip install -e .`, use `esp32-dev` or `python3 -m esp32_dev`. With no subcommand those print help instead of running setup:

```bash
esp32-dev --help
esp32-dev setup --dry-run
```

Default prefix is `~/.esp32-dev`. Override with `--prefix`. Flags, resume after a killed install, and what each step does: [Setup](features/setup.md). Rust details: [Rust](features/rust.md).

## Activate

```bash
source ~/.esp32-dev/activate.sh
python -m esptool
pio --help
idf.py --help
cargo --version
esp-generate --help
```

`activate.sh` exports `ESP32_DEV_PREFIX`, activates the tools virtualenv, sets `IDF_PATH`, sources ESP-IDF `export.sh`, sets `CARGO_HOME` / `RUSTUP_HOME` under the prefix, and sources `export-esp.sh`. `idf.py` needs the IDF export; Xtensa Rust builds need `export-esp.sh`. `pio` and esptool can also be run as `$HOME/.esp32-dev/venv/bin/python -m platformio` and `-m esptool`.

USB serial may need a logout/login after you are added to `dialout`.

## Check the install

```bash
./scripts/setup-esp32-dev.sh status
./scripts/setup-esp32-dev.sh verify
```

`verify` prints the same rows as `status` and exits `1` if git, python3, esptool, PlatformIO, ESP-IDF, or rustup is missing.

Plug in a board and run the smoke test: [Blink](features/blink.md).

## Install the agent skill

So coding agents reuse this prefix instead of pip-installing or cloning the toolchains:

```bash
python3 install.py -a cursor -y          # this project
python3 install.py -g -a cursor -y       # all Cursor projects
```

See [Agent skill](features/agent-skill.md).

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
make lint
make test
```

Docker equivalents and the published CLI image: [Container](features/container.md).
