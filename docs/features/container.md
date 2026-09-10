# Container

Docker images for running tests/lint and for shipping the `esp32-dev` CLI. GitHub Actions builds them; the runtime image is published to GitHub Container Registry.

## Overview

The [Dockerfile](../../Dockerfile) has three stages:

| Stage | Contents | Entry |
|-------|----------|--------|
| `base` | Python 3.12 slim, package sources | none |
| `test` | `pip install -e ".[dev]"`, tests, Makefile, `install.py`, skill tree | `make` (default `test`) |
| `runtime` | `pip install .` (the CLI only) | `esp32-dev` (default `--help`) |

The **runtime** image does not include ESP-IDF, PlatformIO platforms, Rust/espup, or a pre-built `~/.esp32-dev`. It is the installer CLI. Running `setup` inside a container still needs bind-mounted prefix, packages, and (for blink) USB devices.

## Usage

Lint and tests (same as CI):

```bash
docker build --target test -t esp32-dev:test .
docker run --rm esp32-dev:test test
docker run --rm esp32-dev:test lint
```

CLI image:

```bash
docker build --target runtime -t esp32-dev:runtime .
docker run --rm esp32-dev:runtime --help
docker run --rm esp32-dev:runtime setup --dry-run
```

Host development without Docker is `make lint` and `make test` after `pip install -e ".[dev]"`. Coverage must stay at 100% (`pytest-cov` `--cov-fail-under=100`).

## Published image

On `main` and version tags (`v*`), [`.github/workflows/container.yml`](../../.github/workflows/container.yml) builds `linux/amd64` and `linux/arm64` and pushes to:

`ghcr.io/brianlechthaler/esp_dev`

Pull requests build but do not push. Tags include branch, semver, and git sha (see `docker/metadata-action` in that workflow).

```bash
docker pull ghcr.io/brianlechthaler/esp_dev:main
docker run --rm ghcr.io/brianlechthaler/esp_dev:main --help
```

Image name follows the GitHub repository (`brianlechthaler/esp_dev`). GHCR may lowercase the path.

## CI

| Workflow | Trigger | What it runs |
|----------|---------|----------------|
| [test.yml](../../.github/workflows/test.yml) | push/PR to `main` | Build `test` stage, `docker run … test` |
| [lint.yml](../../.github/workflows/lint.yml) | push/PR to `main` | Build `test` stage, `docker run … lint` |
| [container.yml](../../.github/workflows/container.yml) | push/PR to `main`, tags `v*` | Build `runtime` for amd64/arm64; push except on PRs |

Both test and lint jobs cache the image with GitHub Actions cache (`type=gha`).

## Related

- [Getting started](../getting-started.md)
- [Setup](setup.md)
- [Architecture](../architecture.md)
