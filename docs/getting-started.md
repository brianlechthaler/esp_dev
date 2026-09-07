# Getting started

Linux toolkit for **ESP-IDF**, **PlatformIO**, and **esptool**, plus an agent skill so coding tools reuse that install.

## Install the toolkit

```bash
./scripts/setup-esp32-dev.sh
source ~/.esp32-dev/activate.sh
```

That installs ESP-IDF, PlatformIO, and esptool under `~/.esp32-dev`. Preview with `./scripts/setup-esp32-dev.sh setup --dry-run`. Details and flags: [README](../README.md).

Activate in the current shell if you did not source the script:

```bash
source ~/.esp32-dev/activate.sh
python -m esptool
pio --help
idf.py --help
```

## Install the agent skill

So agents use this toolkit instead of downloading pio / ESP-IDF / esptool again:

```bash
python3 install.py -a cursor -y          # this project
python3 install.py -g -a cursor -y       # all your Cursor projects
```

See [Agent skill](features/agent-skill.md).

## Verify

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
make lint
make test
```

Or with Docker:

```bash
docker build --target test -t esp32-dev:test .
docker run --rm esp32-dev:test test
docker run --rm esp32-dev:test lint
```
