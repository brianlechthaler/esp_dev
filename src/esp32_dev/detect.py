"""Linux distribution detection and package-manager helpers."""

from __future__ import annotations

from pathlib import Path

from esp32_dev.config import ARCH_PACKAGES, DEBIAN_PACKAGES, FEDORA_PACKAGES
from esp32_dev.errors import SetupError

FAMILY_DEBIAN = "debian"
FAMILY_FEDORA = "fedora"
FAMILY_ARCH = "arch"

_DEBIAN_IDS = frozenset({"debian", "ubuntu", "raspbian", "linuxmint", "pop", "raspios"})
_FEDORA_IDS = frozenset({"fedora", "rhel", "centos", "rocky", "almalinux"})
_ARCH_IDS = frozenset({"arch", "manjaro", "endeavouros"})


def parse_os_release(text: str) -> dict[str, str]:
    """Parse ``os-release`` file contents into a key/value mapping."""
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        values[key] = _unquote(value.strip())
    return values


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def read_os_release(path: Path) -> dict[str, str]:
    """Read and parse an ``os-release`` file."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SetupError(f"unable to read {path}: {exc}") from exc
    return parse_os_release(text)


def detect_family(data: dict[str, str]) -> str | None:
    """Return a supported distro family, or ``None`` if it is unknown."""
    ident = data.get("ID", "").lower()
    like = data.get("ID_LIKE", "").lower().split()
    if ident in _DEBIAN_IDS or "debian" in like or "ubuntu" in like:
        return FAMILY_DEBIAN
    if ident in _FEDORA_IDS or "fedora" in like or "rhel" in like:
        return FAMILY_FEDORA
    if ident in _ARCH_IDS or "arch" in like:
        return FAMILY_ARCH
    return None


def packages_for(family: str) -> tuple[str, ...]:
    """Return the prerequisite package list for a distro family."""
    if family == FAMILY_DEBIAN:
        return DEBIAN_PACKAGES
    if family == FAMILY_FEDORA:
        return FEDORA_PACKAGES
    if family == FAMILY_ARCH:
        return ARCH_PACKAGES
    raise SetupError(f"unsupported distro family: {family}")
