"""Tests for configuration defaults and validation."""

from pathlib import Path

import pytest

from esp32_dev.config import (
    DEFAULT_PREFIX_NAME,
    default_prefix,
    default_udev_path,
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
    assert config.needs_venv is True
    assert config.skip_shell is False


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


def test_empty_repo_rejected(tmp_path: Path) -> None:
    with pytest.raises(SetupError, match="repository URL must not be empty"):
        make_config(tmp_path, idf_repo=" ")
