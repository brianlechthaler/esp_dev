# ESP32 development environment

Linux installer for **ESP-IDF**, **PlatformIO**, and **esptool**. It puts distro packages, a tools virtualenv, udev rules, and `dialout` membership in one prefix (`~/.esp32-dev` by default).

## Quick start

```bash
. ./scripts/install.sh
```

That installs the toolkit and hooks common shells so new interactive sessions activate it. Sourcing also activates the current bash or zsh session. Running without sourcing still hooks future shells:

```bash
./scripts/install.sh
./scripts/install.sh --dry-run
```

The older wrapper `./scripts/setup-esp32-dev.sh` still works. Full steps: [Getting started](docs/getting-started.md).

## Documentation

- [Getting started](docs/getting-started.md)
- [Architecture](docs/architecture.md)
- [Features](docs/features/)
- [Doc index](docs/index.md)

## Requirements

Linux (Debian/Ubuntu, Fedora/RHEL-family, or Arch-family), Python 3.10+, network access, and sudo for packages, udev, and `dialout`.

## License

[MIT](LICENSE)
