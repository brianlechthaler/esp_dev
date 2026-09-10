"""Tests for os-release parsing and distro family detection."""

from pathlib import Path

import pytest

from esp32_dev.config import (
    ARCH_PACKAGES,
    DEBIAN_PACKAGES,
    FEDORA_PACKAGES,
)
from esp32_dev.detect import (
    FAMILY_ARCH,
    FAMILY_DEBIAN,
    FAMILY_FEDORA,
    detect_family,
    packages_for,
    parse_os_release,
    read_os_release,
)
from esp32_dev.errors import SetupError


def test_parse_os_release_skips_blank_comments_and_invalid() -> None:
    text = """
# comment
ID=debian
ID_LIKE="ubuntu debian"
VERSION='13'
=novalue
UNQUOTED=hello
EMPTY=

"""
    parsed = parse_os_release(text)
    assert parsed["ID"] == "debian"
    assert parsed["ID_LIKE"] == "ubuntu debian"
    assert parsed["VERSION"] == "13"
    assert parsed["UNQUOTED"] == "hello"
    assert parsed["EMPTY"] == ""
    assert "=" not in parsed


def test_read_os_release_success(tmp_path: Path) -> None:
    path = tmp_path / "os-release"
    path.write_text('ID="ubuntu"\n', encoding="utf-8")
    assert read_os_release(path)["ID"] == "ubuntu"


def test_read_os_release_missing(tmp_path: Path) -> None:
    path = tmp_path / "missing"
    with pytest.raises(SetupError, match="unable to read"):
        read_os_release(path)


def test_detect_family_variants() -> None:
    assert detect_family({"ID": "Debian"}) == FAMILY_DEBIAN
    assert detect_family({"ID": "ubuntu"}) == FAMILY_DEBIAN
    assert detect_family({"ID": "other", "ID_LIKE": "debian"}) == FAMILY_DEBIAN
    assert detect_family({"ID": "other", "ID_LIKE": "ubuntu"}) == FAMILY_DEBIAN
    assert detect_family({"ID": "fedora"}) == FAMILY_FEDORA
    assert detect_family({"ID": "other", "ID_LIKE": "rhel fedora"}) == FAMILY_FEDORA
    assert detect_family({"ID": "arch"}) == FAMILY_ARCH
    assert detect_family({"ID": "other", "ID_LIKE": "arch"}) == FAMILY_ARCH
    assert detect_family({"ID": "gentoo"}) is None
    assert detect_family({}) is None


def test_packages_for_known_families() -> None:
    assert packages_for(FAMILY_DEBIAN) == DEBIAN_PACKAGES
    assert packages_for(FAMILY_FEDORA) == FEDORA_PACKAGES
    assert packages_for(FAMILY_ARCH) == ARCH_PACKAGES
    assert "curl" in DEBIAN_PACKAGES
    assert "build-essential" in DEBIAN_PACKAGES
    assert "pkg-config" in DEBIAN_PACKAGES
    assert "libudev-dev" in DEBIAN_PACKAGES
    assert "curl" in FEDORA_PACKAGES
    assert "gcc" in FEDORA_PACKAGES
    assert "perl" in FEDORA_PACKAGES
    assert "curl" in ARCH_PACKAGES
    assert "gcc" in ARCH_PACKAGES


def test_packages_for_unknown() -> None:
    with pytest.raises(SetupError, match="unsupported distro family"):
        packages_for("gentoo")
