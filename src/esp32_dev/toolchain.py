"""Look up and rewrite pinned toolchain versions."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import cast
from urllib.error import URLError
from urllib.request import Request, urlopen

from esp32_dev.errors import SetupError
from esp32_dev.pins import (
    CARGO_ESPFLASH_VERSION,
    ESP_GENERATE_VERSION,
    ESPFLASH_VERSION,
    ESPTOOL_VERSION,
    ESPUP_VERSION,
    IDF_VERSION,
    LDPROXY_VERSION,
    PLATFORMIO_VERSION,
    RUST_VERSION,
)
from esp32_dev.releases import fetch_latest_idf_release_tag, require_https

PIN_NAMES: tuple[str, ...] = (
    "IDF_VERSION",
    "ESPTOOL_VERSION",
    "PLATFORMIO_VERSION",
    "RUST_VERSION",
    "ESPUP_VERSION",
    "LDPROXY_VERSION",
    "ESPFLASH_VERSION",
    "CARGO_ESPFLASH_VERSION",
    "ESP_GENERATE_VERSION",
)

CRATE_FIELDS: tuple[tuple[str, str], ...] = (
    ("espup", "ESPUP_VERSION"),
    ("ldproxy", "LDPROXY_VERSION"),
    ("espflash", "ESPFLASH_VERSION"),
    ("cargo-espflash", "CARGO_ESPFLASH_VERSION"),
    ("esp-generate", "ESP_GENERATE_VERSION"),
)

PYPI_URL = "https://pypi.org/pypi/{name}/json"
CRATES_URL = "https://crates.io/api/v1/crates/{name}"
RUST_STABLE_URL = "https://static.rust-lang.org/dist/channel-rust-stable.toml"
_USER_AGENT = "esp32-dev"
_ASSIGN = re.compile(r'^([A-Z][A-Z0-9_]*) = "([^"]*)"', re.MULTILINE)
_RUST_VERSION = re.compile(r'"(\d+\.\d+\.\d+)')


def current_pins() -> dict[str, str]:
    """Return the versions compiled into ``pins.py``."""
    return {
        "IDF_VERSION": IDF_VERSION,
        "ESPTOOL_VERSION": ESPTOOL_VERSION,
        "PLATFORMIO_VERSION": PLATFORMIO_VERSION,
        "RUST_VERSION": RUST_VERSION,
        "ESPUP_VERSION": ESPUP_VERSION,
        "LDPROXY_VERSION": LDPROXY_VERSION,
        "ESPFLASH_VERSION": ESPFLASH_VERSION,
        "CARGO_ESPFLASH_VERSION": CARGO_ESPFLASH_VERSION,
        "ESP_GENERATE_VERSION": ESP_GENERATE_VERSION,
    }


def pins_path() -> Path:
    """Return the on-disk ``pins.py`` this process imported."""
    import esp32_dev.pins as pins

    return Path(pins.__file__)


def _request(url: str) -> str:
    require_https(url)
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": _USER_AGENT},
    )
    try:
        with urlopen(request, timeout=30) as response:
            return cast(str, response.read().decode("utf-8"))
    except (OSError, URLError) as exc:
        raise SetupError(f"unable to look up toolchain versions: {exc}") from exc


def _load_object(payload: str, label: str) -> dict[str, object]:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise SetupError(f"{label} response was not valid JSON") from exc
    if not isinstance(data, dict):
        raise SetupError(f"{label} response was not an object")
    return data


def fetch_pypi_version(name: str) -> str:
    """Return the current PyPI version for ``name``."""
    data = _load_object(_request(PYPI_URL.format(name=name)), name)
    info = data.get("info")
    if not isinstance(info, dict):
        raise SetupError(f"{name} release did not include package info")
    version = info.get("version")
    if not isinstance(version, str) or not version.strip():
        raise SetupError(f"{name} release did not include a version")
    return version.strip()


def fetch_crate_version(name: str) -> str:
    """Return the newest crates.io version for ``name``."""
    data = _load_object(_request(CRATES_URL.format(name=name)), name)
    crate = data.get("crate")
    if not isinstance(crate, dict):
        raise SetupError(f"{name} release did not include crate metadata")
    version = crate.get("newest_version")
    if not isinstance(version, str) or not version.strip():
        raise SetupError(f"{name} release did not include a version")
    return version.strip()


def parse_rust_stable_version(text: str) -> str:
    """Return the rustc semver from a rustup stable channel manifest."""
    in_pkg = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "[pkg.rust]":
            in_pkg = True
            continue
        if in_pkg and stripped.startswith("["):
            break
        if in_pkg and stripped.startswith("version"):
            match = _RUST_VERSION.search(stripped)
            if match:
                return match.group(1)
    raise SetupError("rustup stable manifest did not include a rustc version")


def fetch_rust_stable_version() -> str:
    """Return the current rustup stable rustc version."""
    return parse_rust_stable_version(_request(RUST_STABLE_URL))


def latest_pins() -> dict[str, str]:
    """Return upstream stable versions keyed like ``current_pins``."""
    return {
        "IDF_VERSION": fetch_latest_idf_release_tag(),
        "ESPTOOL_VERSION": fetch_pypi_version("esptool"),
        "PLATFORMIO_VERSION": fetch_pypi_version("platformio"),
        "RUST_VERSION": fetch_rust_stable_version(),
        "ESPUP_VERSION": fetch_crate_version("espup"),
        "LDPROXY_VERSION": fetch_crate_version("ldproxy"),
        "ESPFLASH_VERSION": fetch_crate_version("espflash"),
        "CARGO_ESPFLASH_VERSION": fetch_crate_version("cargo-espflash"),
        "ESP_GENERATE_VERSION": fetch_crate_version("esp-generate"),
    }


def read_pin_file(path: Path) -> dict[str, str]:
    """Parse version assignments from a ``pins.py`` file."""
    found = dict(_ASSIGN.findall(path.read_text(encoding="utf-8")))
    missing = [name for name in PIN_NAMES if name not in found]
    if missing:
        raise SetupError(f"pins file is missing {', '.join(missing)}")
    return {name: found[name] for name in PIN_NAMES}


def render_pins(values: dict[str, str]) -> str:
    """Render ``pins.py`` from a complete version mapping."""
    missing = [name for name in PIN_NAMES if name not in values]
    if missing:
        raise SetupError(f"cannot render pins without {', '.join(missing)}")
    lines = [
        '"""Pinned installer toolchain versions.',
        "",
        "``scripts/toolchain-versions.py apply`` rewrites the assignment lines below.",
        "Do not duplicate these numbers in docs.",
        '"""',
        "",
    ]
    for name in PIN_NAMES:
        lines.append(f'{name} = "{values[name]}"')
    lines.extend(["", "CARGO_CRATE_VERSIONS: dict[str, str] = {"])
    for crate, field in CRATE_FIELDS:
        lines.append(f'    "{crate}": {field},')
    lines.extend(["}", ""])
    return "\n".join(lines)


def apply_updates(path: Path, latest: dict[str, str]) -> list[tuple[str, str, str]]:
    """Rewrite ``path`` when ``latest`` differs. Return ``(name, old, new)`` rows."""
    current = read_pin_file(path)
    changes = [
        (name, current[name], latest[name]) for name in PIN_NAMES if current[name] != latest[name]
    ]
    if changes:
        path.write_text(render_pins(latest), encoding="utf-8")
    return changes


def format_pins(values: dict[str, str]) -> str:
    """Format pins as ``NAME=value`` lines."""
    return "\n".join(f"{name}={values[name]}" for name in PIN_NAMES)


def main(argv: list[str] | None = None) -> int:
    """Print current pins, print latest pins, or rewrite ``pins.py``."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in {"current", "latest", "apply"}:
        print("usage: toolchain-versions.py {current|latest|apply}", file=sys.stderr)
        return 2
    command = args[0]
    if command == "current":
        print(format_pins(current_pins()))
        return 0
    if command == "latest":
        print(format_pins(latest_pins()))
        return 0
    changes = apply_updates(pins_path(), latest_pins())
    if not changes:
        print("already current")
        return 0
    for name, old, new in changes:
        print(f"updated {name} {old} -> {new}")
    return 0
