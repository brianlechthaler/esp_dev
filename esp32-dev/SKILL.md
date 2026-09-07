---
name: esp32-dev
description: >-
  Uses the shared ESP32 development environment (ESP-IDF, PlatformIO, and
  esptool) already installed by this repo instead of downloading those
  toolchains again. Use when building, flashing, or debugging ESP32 firmware;
  when the user mentions pio, PlatformIO, idf.py, ESP-IDF, esptool, or ESP32
  boards; or when an agent would otherwise pip-install or git-clone those tools.
---

# ESP32 Dev Toolkit

Use the **one** dest environment this repo installs (`~/.esp32-dev` by default). Do not download PlatformIO, ESP-IDF, or esptool into a project, venv, or container when that environment already exists.

## When This Applies

| Applies | Does not apply |
|---------|----------------|
| Build, flash, monitor, or debug ESP32 firmware | Pure docs with no firmware or serial work |
| User or task mentions `pio`, PlatformIO, `idf.py`, ESP-IDF, esptool, or ESP32 | Installing unrelated Python packages |
| Agent is about to `pip install platformio` / `esptool` or `git clone esp-idf` | The user explicitly asks for a throwaway isolated toolchain |

When unsure, **use the shared toolkit**. Only install it once (via this repo) if it is missing.

## Core Rules

1. **Reuse `~/.esp32-dev`** (or `$ESP32_DEV_PREFIX` if set). That prefix holds the tools venv and the ESP-IDF clone.
2. **Do not** `pip install platformio` or `esptool` into the current project.
3. **Do not** `git clone` Espressif ESP-IDF into the project or another home path.
4. **Do not** run PlatformIO's get-platformio installer, Espressif's `install.sh` from a fresh clone, or a second IDF export, unless the shared prefix is missing and you are using this repo's installer.
5. If the toolkit is missing, install it **once** with this repo (`./scripts/setup-esp32-dev.sh` or `python3 -m esp32_dev setup`), then continue. Do not invent a parallel install.

## Workflow

```
ESP32 toolkit:
- [ ] Resolve prefix (~/.esp32-dev or $ESP32_DEV_PREFIX)
- [ ] Confirm activate.sh exists (or run this repo's setup)
- [ ] Source activate.sh (or wrap the command)
- [ ] Run pio / idf.py / python -m esptool
- [ ] Never pip-install or re-clone those tools
```

### 1. Locate the toolkit

Prefix is `$ESP32_DEV_PREFIX` if set, otherwise `$HOME/.esp32-dev`.

```bash
prefix="${ESP32_DEV_PREFIX:-$HOME/.esp32-dev}"
test -f "$prefix/activate.sh"
```

If `activate.sh` is missing, run setup from a clone of this repo (not a one-off pip/git in the firmware project):

```bash
./scripts/setup-esp32-dev.sh
# or: python3 -m esp32_dev setup
python3 -m esp32_dev verify --prefix "${ESP32_DEV_PREFIX:-$HOME/.esp32-dev}"
```

### 2. Activate, then run tools

Interactive or login-capable shell:

```bash
source "${ESP32_DEV_PREFIX:-$HOME/.esp32-dev}/activate.sh"
python -m esptool version
pio --help
idf.py --help
```

Non-interactive (agent default). Prefer the skill wrapper after a local or global skill install:

```bash
# if this skill is installed for Cursor:
~/.cursor/skills/esp32-dev/scripts/with-env.sh pio run
# or from this repo:
./esp32-dev/scripts/with-env.sh python -m esptool chip_id
```

If the wrapper is not on disk, source then exec in one bash:

```bash
bash -lc 'source "$HOME/.esp32-dev/activate.sh" && pio run'
```

Direct binaries without full IDF export (esptool / pio only):

```bash
"$HOME/.esp32-dev/venv/bin/python" -m esptool
"$HOME/.esp32-dev/venv/bin/pio" --help
```

`idf.py` still needs `activate.sh` (it sources ESP-IDF `export.sh`).

### 3. Firmware project vs toolkit repo

Keep PlatformIO / ESP-IDF **project files** (`platformio.ini`, `sdkconfig`, `main/`) in the user's firmware repo. Keep **toolchains** in the shared prefix. A project may live anywhere; only the toolkit is shared.

## Commands

| Task | Command (after activate) |
|------|--------------------------|
| esptool | `python -m esptool …` |
| PlatformIO | `pio run`, `pio run -t upload`, `pio device monitor` |
| ESP-IDF | `idf.py set-target esp32`, `idf.py build`, `idf.py flash`, `idf.py monitor` |
| Toolkit status | `python3 -m esp32_dev status` |
| Toolkit verify | `python3 -m esp32_dev verify` |
| First-time toolkit install | `./scripts/setup-esp32-dev.sh` in this repo |

Useful paths:

| Path | Role |
|------|------|
| `~/.esp32-dev/activate.sh` | POSIX activate (venv + IDF) |
| `~/.esp32-dev/venv` | esptool + PlatformIO |
| `~/.esp32-dev/esp-idf` | ESP-IDF (`IDF_PATH`) |

## Anti-Patterns

| Avoid | Do instead |
|-------|------------|
| `pip install platformio esptool` in the project venv | Shared `~/.esp32-dev/venv` via `activate.sh` |
| `git clone https://github.com/espressif/esp-idf` into the firmware repo | Use `~/.esp32-dev/esp-idf` |
| Downloading get-platformio.py / a new IDF toolchain | This repo's `setup` if tools are missing |
| Copying ESP-IDF or `.platformio` into the project for "portability" | Point the agent at the shared prefix |
| Assuming `pio` / `idf.py` on the default PATH | Source `activate.sh` first |

## Additional Resources

- Command examples: [examples.md](examples.md)
- Wrapper script: `scripts/with-env.sh`
