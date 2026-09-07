# ESP32 development environment

Linux installer for **ESP-IDF**, **PlatformIO**, and **esptool**. It puts distro packages, a tools virtualenv, udev rules, and `dialout` membership in one prefix (`~/.esp32-dev` by default).

## Quick start

```bash
./scripts/setup-esp32-dev.sh
source ~/.esp32-dev/activate.sh
```

Preview without changing the system: `./scripts/setup-esp32-dev.sh setup --dry-run`.

Full steps, distro support, and activation: [Getting started](docs/getting-started.md).

## Documentation

- [Getting started](docs/getting-started.md)
- [Architecture](docs/architecture.md)
- [Features](docs/features/)
- [Doc index](docs/index.md)

## Requirements

Linux (Debian/Ubuntu, Fedora/RHEL-family, or Arch-family), Python 3.10+, network access, and sudo for packages, udev, and `dialout`.

## License

[MIT](LICENSE)
