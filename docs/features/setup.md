# Setup

Installs host packages, a tools virtualenv (esptool and PlatformIO), ESP-IDF, the Espressif Rust toolchain, udev rules, and `dialout` membership, then writes `activate.sh`.

## Overview

`setup` and `resume` run the same code. Both start by deleting leftover `*.partial` staging directories and incomplete `esp-idf` / `venv` / `cargo` trees, then continue. A complete ESP-IDF clone is kept: git fetch/checkout, submodule update, and `install.sh` run again. An existing rustup under the prefix is kept: components, RISC-V targets, and missing cargo crates are refreshed.

Linux and Python 3.10+ are required. Default prefix is `~/.esp32-dev`.

ESP-IDF version defaults to the latest GitHub release (`latest` or `stable` are aliases). Pin a tag with `--idf-version v6.1`. esptool and PlatformIO are `pip install --upgrade` with no upper bound. Rust uses the official rustup installer plus `espup` (see [Rust](rust.md)).

ESP-IDF is cloned with `--depth 1` and shallow submodules. Use `--full-idf-clone` for full history. Git clone/fetch progress is streamed.

## Usage

```bash
. ./scripts/install.sh
./scripts/install.sh --dry-run
./scripts/setup-esp32-dev.sh
./scripts/setup-esp32-dev.sh setup --dry-run
./scripts/setup-esp32-dev.sh resume
./scripts/setup-esp32-dev.sh setup --prefix /opt/esp32-dev --idf-targets esp32,esp32s3
python3 -m esp32_dev setup --skip-idf --skip-packages
```

`scripts/install.sh` runs `setup` and writes shell rc hooks so new interactive shells source `activate.sh`. Source it (`. ./scripts/install.sh`) to activate the current bash or zsh session too. Pass `--skip-shell` to skip the rc hooks. See [Getting started](../getting-started.md).

### Status and verify

```bash
./scripts/setup-esp32-dev.sh status
./scripts/setup-esp32-dev.sh verify --prefix ~/.esp32-dev
```

Both print one row per check: git, cmake, ninja, python3, venv, esptool, platformio, esp-idf, rustup, cargo, espup, udev, dialout. `status` always exits 0 (unless the command itself fails). `verify` exits 1 if any of git, python3, esptool, platformio, esp-idf, or rustup is missing. cmake, ninja, cargo, espup, udev, and dialout are reported but not required for a passing `verify`.

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `--prefix` | `~/.esp32-dev` | Install root |
| `--idf-version` | `latest` | ESP-IDF git branch or tag; `latest`/`stable` query GitHub |
| `--idf-repo` | `https://github.com/espressif/esp-idf.git` | Clone URL |
| `--idf-targets` | `esp32` | Comma-separated chips passed to ESP-IDF `install.sh` |
| `--skip-packages` | off | Do not install distro packages |
| `--skip-esptool` | off | Do not pip-install esptool |
| `--skip-platformio` | off | Do not pip-install PlatformIO |
| `--skip-idf` | off | Do not clone or install ESP-IDF |
| `--skip-rust` | off | Do not install rustup, espup, or ESP Rust cargo tools |
| `--skip-udev` | off | Do not write udev rules |
| `--skip-dialout` | off | Do not add the user to `dialout` |
| `--skip-shell` | off | Do not add auto-activation hooks to shell rc files |
| `--no-sudo` | off | Never prefix commands with sudo |
| `--dry-run` | off | Log actions; do not change the system |
| `--force` | off | Reinstall components even if they look present |
| `--full-idf-clone` | off | Full git history and recursive submodules |

If both `--skip-esptool` and `--skip-platformio` are set, the tools virtualenv is not created.

`--verbose` / `--quiet` apply to the whole CLI. They cannot be combined.

## Distro packages

| Family | Detected IDs (and `ID_LIKE`) | Installer |
|--------|------------------------------|-----------|
| Debian | debian, ubuntu, raspbian, linuxmint, pop, raspios | `apt-get` |
| Fedora | fedora, rhel, centos, rocky, almalinux | `dnf` or `yum` |
| Arch | arch, manjaro, endeavouros | `pacman` |

Unknown distro: the command fails and prints the Debian package list. Install those (or equivalents) yourself and pass `--skip-packages`.

Missing `git`/`cmake`/`ninja` after package install (when IDF is not skipped) also fails. Missing `gcc` or `curl`/`wget` (when Rust is not skipped) also fails.

## udev and serial

Rules go to `/etc/udev/rules.d/99-esp32-dev.rules` and cover CP210x, CH340, CH9102/CH342, FTDI FT232, and Espressif USB Serial/JTAG (`idVendor` 303a). `udevadm control --reload-rules` and `trigger` run when `udevadm` is on `PATH`.

If the `dialout` group exists and the current user is not in it, setup runs `usermod -aG dialout`. Log out and back in before using USB serial.

## Troubleshooting

**`unsupported OS`**: not Linux. Run on a Linux host or VM.

**`unsupported Linux distribution`**: install packages by hand, then `--skip-packages`.

**`unable to look up the latest ESP-IDF release`**: GitHub API unreachable. Pass a concrete `--idf-version` (for example `v5.4.1`).

**Killed mid-clone**: re-run `setup` or `resume`. Incomplete trees are removed; a usable clone is reused. An incomplete `cargo/` tree (no `rustup` binary) is also removed.

**USB permission denied**: confirm `status` shows dialout OK, then log out/in. Confirm the udev file exists.

**`idf.py` not found after activate**: ESP-IDF `export.sh` is bash-specific. Use bash, and do not skip IDF if you need `idf.py`.

**`cargo` not found after activate**: rustup lives under the prefix. Re-run setup without `--skip-rust`, then `source` `activate.sh`.

## Related

- [Getting started](../getting-started.md)
- [Architecture](../architecture.md)
- [Rust](rust.md)
- [Blink](blink.md)
- [Agent skill](agent-skill.md)
