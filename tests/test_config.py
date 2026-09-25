"""Tests for configuration defaults and validation."""

from pathlib import Path

import pytest

from esp32_dev.config import (
    DEFAULT_PREFIX_NAME,
    default_prefix,
    default_udev_path,
    rustup_triple,
    validate_idf_repo,
    validate_idf_version,
)
from esp32_dev.errors import SetupError
from tests.conftest import make_config


def test_default_prefix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("esp32_dev.config.Path.home", lambda: tmp_path)
    assert default_prefix() == tmp_path / DEFAULT_PREFIX_NAME


def test_default_udev_path() -> None:
    assert default_udev_path() == Path("/etc/udev/rules.d/99-esp32-dev.rules")


def test_config_paths_and_needs_venv(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert config.venv_dir == config.prefix / "venv"
    assert config.venv_python == config.venv_dir / "bin" / "python"
    assert config.idf_dir == config.prefix / "esp-idf"
    assert config.idf_partial_dir == config.prefix / "esp-idf.partial"
    assert config.venv_partial_dir == config.prefix / "venv.partial"
    assert config.activate_script == config.prefix / "activate.sh"
    assert config.activate_fish == config.prefix / "activate.fish"
    assert config.cargo_home == config.prefix / "cargo"
    assert config.rustup_home == config.prefix / "rustup"
    assert config.cargo_bin == config.prefix / "cargo" / "bin"
    assert config.export_esp_script == config.prefix / "export-esp.sh"
    assert config.needs_venv is True
    assert config.skip_shell is False
    assert config.skip_rust is False


def test_needs_venv_false_when_both_skipped(tmp_path: Path) -> None:
    config = make_config(tmp_path, skip_esptool=True, skip_platformio=True)
    assert config.needs_venv is False


def test_strips_version_and_repo(tmp_path: Path) -> None:
    config = make_config(tmp_path, idf_version="  v6.1  ", idf_repo="  https://example/idf  ")
    assert config.idf_version == "v6.1"
    assert config.idf_repo == "https://example/idf"


def test_empty_targets_rejected(tmp_path: Path) -> None:
    with pytest.raises(SetupError, match="at least one ESP-IDF target"):
        make_config(tmp_path, idf_targets=("  ", ""))


def test_empty_version_rejected(tmp_path: Path) -> None:
    with pytest.raises(SetupError, match="version must not be empty"):
        make_config(tmp_path, idf_version="  ")


def test_idf_ref_and_repo_reject_options(tmp_path: Path) -> None:
    assert validate_idf_version("v6.1") == "v6.1"
    assert validate_idf_version("release/v5.2") == "release/v5.2"
    with pytest.raises(SetupError, match="invalid ESP-IDF version"):
        validate_idf_version("--upload-pack=touch")
    with pytest.raises(SetupError, match="invalid ESP-IDF version"):
        make_config(tmp_path, idf_version="--branch")
    assert validate_idf_repo("https://github.com/espressif/esp-idf.git").startswith("https://")
    assert validate_idf_repo("git@github.com:espressif/esp-idf.git").startswith("git@")
    with pytest.raises(SetupError, match="https or git@"):
        validate_idf_repo("file:///tmp/idf")
    with pytest.raises(SetupError, match="invalid ESP-IDF repository"):
        make_config(tmp_path, idf_repo="-https://example.test/idf")


def test_rustup_triple_rejects_unknown_cpu() -> None:
    assert rustup_triple("x86_64") == "x86_64-unknown-linux-gnu"
    assert rustup_triple("arm64") == "aarch64-unknown-linux-gnu"
    with pytest.raises(SetupError, match="unsupported CPU"):
        rustup_triple("riscv64")


def test_empty_repo_rejected(tmp_path: Path) -> None:
    with pytest.raises(SetupError, match="repository URL must not be empty"):
        make_config(tmp_path, idf_repo=" ")
