"""Tests for installer steps and orchestration."""

from __future__ import annotations

from pathlib import Path

import pytest

from esp32_dev.config import ESPTOOL_SPEC, PLATFORMIO_SPEC, UDEV_RULES
from esp32_dev.errors import SetupError
from esp32_dev.installer import (
    ToolStatus,
    _can_write,
    _existing_udev_text,
    _finalize_directory,
    _mkdir,
    _module_status,
    _reload_udev,
    _remove_path,
    _rmtree,
    _run_idf_install,
    _write_text,
    cleanup_stale_install,
    collect_status,
    ensure_dialout,
    ensure_linux,
    ensure_python,
    ensure_required_commands,
    ensure_venv,
    format_status,
    generate_activate_script,
    idf_clone_args,
    idf_fetch_args,
    idf_submodule_args,
    install_esp_idf,
    install_esptool,
    install_packages,
    install_platformio,
    install_udev,
    is_usable_idf_clone,
    next_steps,
    run_setup,
    user_in_group,
    verify_ok,
)
from esp32_dev.process import CommandResult
from tests.conftest import FakeHost, FakeRunner, make_config


def test_ensure_linux_rejects_other_os(tmp_path: Path) -> None:
    host = FakeHost(tmp_path, system_name="Darwin")
    with pytest.raises(SetupError, match="unsupported OS"):
        ensure_linux(host)


def test_ensure_python_rejects_old_version(tmp_path: Path) -> None:
    host = FakeHost(tmp_path, version=(3, 9))
    with pytest.raises(SetupError, match=r"Python 3\.10"):
        ensure_python(host)


def test_user_in_group_paths(tmp_path: Path) -> None:
    missing = FakeHost(tmp_path, groups={})
    assert user_in_group(missing, "dialout") is False
    by_gid = FakeHost(tmp_path, gid_value=20, groups={"dialout": (20, [])})
    assert user_in_group(by_gid, "dialout") is True
    by_name = FakeHost(tmp_path, gid_value=1000, groups={"dialout": (20, ["tester"])})
    assert user_in_group(by_name, "dialout") is True
    outsider = FakeHost(tmp_path, gid_value=1000, groups={"dialout": (20, ["other"])})
    assert user_in_group(outsider, "dialout") is False


def test_generate_activate_and_next_steps(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    script = generate_activate_script(config)
    assert str(config.prefix) in script
    assert "IDF_PATH" in script
    message = next_steps(config)
    assert "source " in message
    assert str(config.activate_script) in message
    assert "python -m esp32_dev blink" in message


def test_format_status_and_verify() -> None:
    assert format_status([]) == "no status items"
    items = [
        ToolStatus("git", True, "/usr/bin/git"),
        ToolStatus("python3", True, "/usr/bin/python3"),
        ToolStatus("esptool", True, "v4"),
        ToolStatus("platformio", True, "v6"),
        ToolStatus("esp-idf", True, "/idf"),
        ToolStatus("extra", False, "nope"),
    ]
    rendered = format_status(items)
    assert "OK" in rendered
    assert "MISSING" in rendered
    assert verify_ok(items) is True
    items[0] = ToolStatus("git", False, "missing")
    assert verify_ok(items) is False
    assert verify_ok([ToolStatus("python3", True, "ok")]) is False


def test_remove_path_and_finalize(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    _remove_path(missing, dry_run=False)
    assert not missing.exists()
    file_path = tmp_path / "file.txt"
    file_path.write_text("x", encoding="utf-8")
    _remove_path(file_path, dry_run=True)
    assert file_path.exists()
    _remove_path(file_path, dry_run=False)
    assert not file_path.exists()
    directory = tmp_path / "dir"
    directory.mkdir()
    (directory / "inner").write_text("y", encoding="utf-8")
    _remove_path(directory, dry_run=False)
    assert not directory.exists()
    target = tmp_path / "target"
    target.write_text("keep", encoding="utf-8")
    link = tmp_path / "link"
    link.symlink_to(target)
    _remove_path(link, dry_run=False)
    assert not link.exists()
    assert target.exists()
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "ok").write_text("z", encoding="utf-8")
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "old").write_text("old", encoding="utf-8")
    _finalize_directory(staging, dest, dry_run=True)
    assert staging.exists()
    _finalize_directory(staging, dest, dry_run=False)
    assert not staging.exists()
    assert (dest / "ok").read_text(encoding="utf-8") == "z"
    assert not (dest / "old").exists()


def test_is_usable_idf_clone(tmp_path: Path) -> None:
    dest = tmp_path / "esp-idf"
    assert is_usable_idf_clone(dest) is False
    dest.mkdir()
    assert is_usable_idf_clone(dest) is False
    (dest / ".git").mkdir()
    assert is_usable_idf_clone(dest) is False
    (dest / "install.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    assert is_usable_idf_clone(dest) is False
    (dest / "export.sh").write_text("#\n", encoding="utf-8")
    assert is_usable_idf_clone(dest) is True
    file_dest = tmp_path / "not-a-dir"
    file_dest.write_text("x", encoding="utf-8")
    assert is_usable_idf_clone(file_dest) is False


def test_cleanup_stale_install(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    cleanup_stale_install(config, dry_run=False)
    config.prefix.mkdir()
    partial = config.prefix / "esp-idf.partial"
    partial.mkdir()
    (partial / "junk").write_text("x", encoding="utf-8")
    stale_file = config.prefix / "venv.partial"
    stale_file.write_text("y", encoding="utf-8")
    config.idf_dir.mkdir()
    (config.idf_dir / "half").write_text("z", encoding="utf-8")
    config.venv_dir.mkdir()
    cleanup_stale_install(config, dry_run=True)
    assert partial.exists()
    cleanup_stale_install(config, dry_run=False)
    assert not partial.exists()
    assert not stale_file.exists()
    assert not config.idf_dir.exists()
    assert not config.venv_dir.exists()
    config.idf_dir.mkdir()
    (config.idf_dir / ".git").mkdir()
    (config.idf_dir / "install.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    (config.idf_dir / "export.sh").write_text("#\n", encoding="utf-8")
    cleanup_stale_install(config, dry_run=False)
    assert config.idf_dir.exists()


def test_cleanup_prefix_iterdir_oserror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = make_config(tmp_path)
    config.prefix.mkdir()

    def boom(self: Path) -> list[Path]:
        raise OSError("denied")

    monkeypatch.setattr(Path, "iterdir", boom)
    cleanup_stale_install(config, dry_run=False)


def test_rmtree_mkdir_write_dry_and_real(tmp_path: Path) -> None:
    target = tmp_path / "tree"
    target.mkdir()
    (target / "file").write_text("x", encoding="utf-8")
    _rmtree(target, dry_run=True)
    assert target.exists()
    _rmtree(target, dry_run=False)
    assert not target.exists()
    nested = tmp_path / "a" / "b"
    _mkdir(nested, dry_run=True)
    assert not nested.exists()
    _mkdir(nested, dry_run=False)
    assert nested.is_dir()
    file_path = tmp_path / "out" / "note.txt"
    _write_text(file_path, "hi", dry_run=True)
    assert not file_path.exists()
    _write_text(file_path, "hi", dry_run=False)
    assert file_path.read_text(encoding="utf-8") == "hi"


def test_can_write_oserror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "rules"

    def boom(_path: str, _mode: int) -> bool:
        raise OSError("denied")

    monkeypatch.setattr("esp32_dev.installer.os.access", boom)
    assert _can_write(path) is False


def test_can_write_success(tmp_path: Path) -> None:
    assert _can_write(tmp_path / "writable.txt") is True


def test_ensure_required_commands_missing(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    runner = FakeRunner()
    runner.which_map["git"] = None
    with pytest.raises(SetupError, match="missing required commands: git"):
        ensure_required_commands(config, runner)


def test_ensure_required_commands_skip_idf_only_python3(tmp_path: Path) -> None:
    config = make_config(tmp_path, skip_idf=True)
    runner = FakeRunner()
    runner.which_map = {"python3": "/usr/bin/python3"}
    ensure_required_commands(config, runner)


def test_install_packages_unsupported_distro(tmp_path: Path) -> None:
    host = FakeHost(tmp_path, os_release="ID=gentoo\n")
    with pytest.raises(SetupError, match="unsupported Linux distribution"):
        install_packages(make_config(tmp_path), FakeRunner(), host)


def test_install_packages_already_present(tmp_path: Path) -> None:
    runner = FakeRunner()
    install_packages(make_config(tmp_path), runner, FakeHost(tmp_path))
    assert not runner.has_args("apt-get", "install")


def test_install_packages_debian_missing(tmp_path: Path) -> None:
    runner = FakeRunner()
    runner.missing_packages.add("cmake")
    install_packages(make_config(tmp_path), runner, FakeHost(tmp_path))
    assert runner.has_args("apt-get", "update")
    assert runner.has_args("apt-get", "install", "-y", "cmake")


def test_install_packages_force_reinstalls_all(tmp_path: Path) -> None:
    runner = FakeRunner()
    config = make_config(tmp_path, force=True)
    install_packages(config, runner, FakeHost(tmp_path))
    assert runner.has_args("apt-get", "install")


def test_install_packages_fedora_dnf_and_yum(tmp_path: Path) -> None:
    host = FakeHost(tmp_path, os_release="ID=fedora\n")
    runner = FakeRunner()
    runner.missing_packages.add("cmake")
    install_packages(make_config(tmp_path), runner, host)
    assert runner.has_args("dnf", "install", "-y", "cmake")

    yum_runner = FakeRunner()
    yum_runner.which_map["dnf"] = None
    yum_runner.missing_packages.add("git")
    install_packages(make_config(tmp_path), yum_runner, host)
    assert yum_runner.has_args("yum", "install", "-y", "git")


def test_install_packages_arch(tmp_path: Path) -> None:
    host = FakeHost(tmp_path, os_release="ID=arch\n")
    runner = FakeRunner()
    runner.missing_packages.add("ninja")
    install_packages(make_config(tmp_path), runner, host)
    assert runner.has_args("pacman", "-S", "--noconfirm", "--needed", "ninja")


def test_ensure_venv_reuses_existing_python(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.venv_python.parent.mkdir(parents=True)
    config.venv_python.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    runner = FakeRunner()
    python_path = ensure_venv(config, runner, FakeHost(tmp_path))
    assert python_path.is_file()
    assert not runner.has_args("/usr/bin/python3", "-m", "venv")
    assert runner.has_args(str(python_path), "-m", "pip", "install", "--upgrade", "pip")


def test_ensure_venv_creates_and_upgrades_pip(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    runner = FakeRunner()
    python_path = ensure_venv(config, runner, FakeHost(tmp_path))
    assert python_path.is_file()
    assert runner.has_args("/usr/bin/python3", "-m", "venv")
    assert runner.has_args(str(python_path), "-m", "pip", "install", "--upgrade", "pip")


def test_ensure_venv_recreates_broken_dir(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.venv_dir.mkdir(parents=True)
    (config.venv_dir / "stale").write_text("x", encoding="utf-8")
    runner = FakeRunner()
    ensure_venv(config, runner, FakeHost(tmp_path))
    assert config.venv_python.is_file()


def test_ensure_venv_force_removes_existing(tmp_path: Path) -> None:
    config = make_config(tmp_path, force=True)
    config.venv_dir.mkdir(parents=True)
    python = config.venv_python
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_text("old", encoding="utf-8")
    runner = FakeRunner()
    ensure_venv(config, runner, FakeHost(tmp_path))
    assert runner.has_args("/usr/bin/python3", "-m", "venv")


def test_ensure_venv_dry_run_skips_pip(tmp_path: Path) -> None:
    config = make_config(tmp_path, dry_run=True)
    runner = FakeRunner(dry_run=True)
    ensure_venv(config, runner, FakeHost(tmp_path))
    assert not runner.has_args("/usr/bin/python3", "-m", "pip")


def test_ensure_venv_fails_when_python_missing(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    runner = FakeRunner(apply_side_effects=False)
    with pytest.raises(SetupError, match="failed to create venv python"):
        ensure_venv(config, runner, FakeHost(tmp_path))


def test_pip_install_helpers(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    runner = FakeRunner()
    python_path = ensure_venv(config, runner, FakeHost(tmp_path))
    install_esptool(runner, python_path)
    install_platformio(runner, python_path)
    assert any(ESPTOOL_SPEC in " ".join(call["args"]) for call in runner.calls)  # type: ignore[arg-type]
    assert any(PLATFORMIO_SPEC in " ".join(call["args"]) for call in runner.calls)  # type: ignore[arg-type]


def test_idf_install_missing_script(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.idf_dir.mkdir(parents=True)
    with pytest.raises(SetupError, match="install script missing"):
        _run_idf_install(config, FakeRunner())


def test_idf_install_dry_run_without_script(tmp_path: Path) -> None:
    config = make_config(tmp_path, dry_run=True)
    runner = FakeRunner(dry_run=True)
    _run_idf_install(config, runner)
    assert runner.has_args("bash")


def test_idf_git_args_shallow_and_full(tmp_path: Path) -> None:
    dest = tmp_path / "esp-idf"
    shallow = make_config(tmp_path)
    full = make_config(tmp_path, shallow_idf=False)
    shallow_clone = idf_clone_args(shallow, dest)
    assert "--depth" in shallow_clone
    assert "--shallow-submodules" in shallow_clone
    assert "--recursive" not in shallow_clone
    full_clone = idf_clone_args(full, dest)
    assert "--depth" not in full_clone
    assert "--recursive" in full_clone
    assert "--depth" in idf_fetch_args(shallow)
    assert "--depth" not in idf_fetch_args(full)
    assert "--depth" in idf_submodule_args(shallow)
    assert "--depth" not in idf_submodule_args(full)


def test_install_esp_idf_clone(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    runner = FakeRunner()
    install_esp_idf(config, runner)
    assert runner.has_args(
        "git", "clone", "--progress", "--branch", config.idf_version, "--depth", "1"
    )
    assert (config.idf_dir / "install.sh").is_file()
    assert runner.has_args("bash", str(config.idf_dir / "install.sh"), "esp32")
    clone_calls = [call for call in runner.calls if call["args"][:2] == ["git", "clone"]]
    assert clone_calls[0]["stream"] is True
    assert clone_calls[0]["args"][-1] == str(config.idf_partial_dir)
    assert not config.idf_partial_dir.exists()


def test_install_esp_idf_resolves_latest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("esp32_dev.releases.fetch_latest_idf_release_tag", lambda: "v6.1")
    config = make_config(tmp_path, idf_version="latest")
    runner = FakeRunner()
    install_esp_idf(config, runner)
    assert config.idf_version == "v6.1"
    assert runner.has_args("git", "clone", "--progress", "--branch", "v6.1", "--depth", "1")


def test_install_esp_idf_full_clone(tmp_path: Path) -> None:
    config = make_config(tmp_path, shallow_idf=False)
    runner = FakeRunner()
    install_esp_idf(config, runner)
    assert runner.has_args(
        "git", "clone", "--progress", "--branch", config.idf_version, "--recursive"
    )
    assert not runner.has_args(
        "git", "clone", "--progress", "--branch", config.idf_version, "--depth", "1"
    )


def test_install_esp_idf_update_existing_git(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.idf_dir.mkdir(parents=True)
    (config.idf_dir / ".git").mkdir()
    (config.idf_dir / "install.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    (config.idf_dir / "export.sh").write_text("# export\n", encoding="utf-8")
    runner = FakeRunner()
    install_esp_idf(config, runner)
    assert runner.has_args("git", "fetch", "--progress", "--depth", "1")
    assert runner.has_args("git", "checkout")
    assert runner.has_args("git", "submodule", "update", "--init", "--recursive", "--depth", "1")
    assert not runner.has_args("git", "clone")


def test_install_esp_idf_update_full_history(tmp_path: Path) -> None:
    config = make_config(tmp_path, shallow_idf=False)
    config.idf_dir.mkdir(parents=True)
    (config.idf_dir / ".git").mkdir()
    (config.idf_dir / "install.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    (config.idf_dir / "export.sh").write_text("# export\n", encoding="utf-8")
    runner = FakeRunner()
    install_esp_idf(config, runner)
    assert runner.has_args("git", "fetch", "--progress", "origin", config.idf_version)
    assert runner.has_args("git", "submodule", "update", "--init", "--recursive")
    assert not runner.has_args("git", "fetch", "--progress", "--depth", "1")


def test_install_esp_idf_cleans_incomplete_non_git(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.idf_dir.mkdir(parents=True)
    (config.idf_dir / "stale").write_text("x", encoding="utf-8")
    runner = FakeRunner()
    install_esp_idf(config, runner)
    assert runner.has_args("git", "clone")
    assert (config.idf_dir / "install.sh").is_file()


def test_install_esp_idf_cleans_leftover_staging(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.idf_partial_dir.mkdir(parents=True)
    (config.idf_partial_dir / "junk").write_text("x", encoding="utf-8")
    runner = FakeRunner()
    install_esp_idf(config, runner)
    assert runner.has_args("git", "clone")
    assert not config.idf_partial_dir.exists()
    assert (config.idf_dir / "install.sh").is_file()


def test_install_esp_idf_replaces_file_and_symlink(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.prefix.mkdir()
    config.idf_dir.write_text("not a clone", encoding="utf-8")
    runner = FakeRunner()
    install_esp_idf(config, runner)
    assert (config.idf_dir / "install.sh").is_file()

    other = make_config(tmp_path / "other")
    other.prefix.mkdir(parents=True)
    other.idf_dir.symlink_to(tmp_path / "missing-idf")
    other.idf_partial_dir.symlink_to(tmp_path / "missing-partial")
    install_esp_idf(other, FakeRunner())
    assert (other.idf_dir / "install.sh").is_file()
    assert not other.idf_partial_dir.exists()


def test_install_esp_idf_force_reclones(tmp_path: Path) -> None:
    config = make_config(tmp_path, force=True)
    config.idf_dir.mkdir(parents=True)
    (config.idf_dir / ".git").mkdir()
    (config.idf_dir / "install.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    (config.idf_dir / "export.sh").write_text("# export\n", encoding="utf-8")
    runner = FakeRunner()
    install_esp_idf(config, runner)
    assert runner.has_args("git", "clone")
    assert not runner.has_args("git", "fetch")


def test_reload_udev_with_and_without_udevadm(tmp_path: Path) -> None:
    runner = FakeRunner()
    _reload_udev(runner)
    assert runner.has_args("/usr/bin/udevadm", "control", "--reload-rules")
    assert runner.has_args("/usr/bin/udevadm", "trigger")
    missing = FakeRunner()
    missing.which_map["udevadm"] = None
    _reload_udev(missing)
    assert not missing.has_args("/usr/bin/udevadm")


def test_existing_udev_text_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    missing = tmp_path / "nope"
    assert _existing_udev_text(missing) is None
    path = tmp_path / "rules"
    path.write_text("abc", encoding="utf-8")
    assert _existing_udev_text(path) == "abc"

    def boom(self: Path, encoding: str = "utf-8") -> str:
        raise OSError("unreadable")

    monkeypatch.setattr(Path, "read_text", boom)
    assert _existing_udev_text(path) is None


def test_install_udev_already_present(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.udev_rules_path.parent.mkdir(parents=True)
    config.udev_rules_path.write_text(UDEV_RULES, encoding="utf-8")
    runner = FakeRunner()
    install_udev(config, runner)
    assert not runner.has_args("tee")


def test_install_udev_dry_run(tmp_path: Path) -> None:
    config = make_config(tmp_path, dry_run=True)
    runner = FakeRunner(dry_run=True)
    install_udev(config, runner)
    assert not config.udev_rules_path.exists()


def test_install_udev_direct_write(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.udev_rules_path.parent.mkdir(parents=True)
    runner = FakeRunner()
    install_udev(config, runner)
    assert config.udev_rules_path.read_text(encoding="utf-8") == UDEV_RULES


def test_install_udev_via_tee(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = make_config(tmp_path)
    runner = FakeRunner()
    monkeypatch.setattr("esp32_dev.installer._can_write", lambda _path: False)
    install_udev(config, runner)
    assert runner.has_args("mkdir", "-p")
    assert runner.has_args("tee", str(config.udev_rules_path))
    tee_calls = [call for call in runner.calls if call["args"][:1] == ["tee"]]
    assert tee_calls[0]["stdin"] == UDEV_RULES


def test_install_udev_force_overwrites(tmp_path: Path) -> None:
    config = make_config(tmp_path, force=True)
    config.udev_rules_path.parent.mkdir(parents=True)
    config.udev_rules_path.write_text(UDEV_RULES, encoding="utf-8")
    runner = FakeRunner()
    install_udev(config, runner)
    assert config.udev_rules_path.read_text(encoding="utf-8") == UDEV_RULES


def test_ensure_dialout_missing_group(tmp_path: Path) -> None:
    host = FakeHost(tmp_path, groups={})
    runner = FakeRunner()
    ensure_dialout(runner, host)
    assert not runner.has_args("usermod")


def test_ensure_dialout_already_member(tmp_path: Path) -> None:
    runner = FakeRunner()
    ensure_dialout(runner, FakeHost(tmp_path))
    assert not runner.has_args("usermod")


def test_ensure_dialout_adds_user(tmp_path: Path) -> None:
    host = FakeHost(tmp_path, groups={"dialout": (20, ["other"])}, gid_value=1000)
    runner = FakeRunner()
    ensure_dialout(runner, host)
    assert runner.has_args("usermod", "-aG", "dialout", "tester")


def test_module_status_without_venv(tmp_path: Path) -> None:
    status = _module_status(FakeRunner(), tmp_path / "missing-python", "esptool", ["version"])
    assert status.ok is False
    assert "venv python missing" in status.detail


def test_module_status_nonzero(tmp_path: Path) -> None:
    python = tmp_path / "python"
    python.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    runner = FakeRunner()
    runner.module_versions["esptool"] = CommandResult(1, "", "boom")
    status = _module_status(runner, python, "esptool", ["version"])
    assert status.ok is False
    assert "boom" in status.detail
    runner.module_versions["esptool"] = CommandResult(4, "  ", "  ")
    empty = _module_status(runner, python, "esptool", ["version"])
    assert empty.ok is False
    assert "exit 4" in empty.detail


def test_collect_status_all_ok(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    runner = FakeRunner()
    ensure_venv(config, runner, FakeHost(tmp_path))
    config.idf_dir.mkdir(parents=True)
    (config.idf_dir / "tools").mkdir()
    (config.idf_dir / "export.sh").write_text("#\n", encoding="utf-8")
    (config.idf_dir / "tools" / "idf.py").write_text("#\n", encoding="utf-8")
    config.udev_rules_path.parent.mkdir(parents=True)
    config.udev_rules_path.write_text(UDEV_RULES, encoding="utf-8")
    items = collect_status(config, runner, FakeHost(tmp_path))
    by_name = {item.name: item for item in items}
    assert by_name["esptool"].ok
    assert by_name["platformio"].ok
    assert by_name["esp-idf"].ok
    assert by_name["udev"].ok
    assert by_name["dialout"].ok
    assert by_name["venv"].ok


def test_collect_status_missing_tools(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    runner = FakeRunner()
    runner.which_map["cmake"] = None
    items = collect_status(config, runner, FakeHost(tmp_path, groups={}))
    by_name = {item.name: item for item in items}
    assert by_name["cmake"].ok is False
    assert by_name["esptool"].ok is False
    assert by_name["esp-idf"].ok is False
    assert by_name["udev"].ok is False
    assert by_name["dialout"].ok is False


def test_run_setup_full(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    runner = FakeRunner()
    host = FakeHost(tmp_path, groups={"dialout": (20, ["other"])}, gid_value=1000)
    runner.missing_packages.add("wget")
    run_setup(config, runner, host)
    assert runner.has_args("apt-get", "install")
    assert runner.has_args("git", "clone")
    assert config.activate_script.is_file()
    assert config.activate_fish.is_file()
    assert config.venv_python.is_file()
    assert runner.has_args("usermod")
    assert (tmp_path / ".bashrc").is_file()


def test_run_setup_all_skips(tmp_path: Path) -> None:
    config = make_config(
        tmp_path,
        skip_packages=True,
        skip_esptool=True,
        skip_platformio=True,
        skip_idf=True,
        skip_udev=True,
        skip_dialout=True,
        skip_shell=True,
    )
    runner = FakeRunner()
    run_setup(config, runner, FakeHost(tmp_path))
    assert not runner.has_args("apt-get")
    assert not runner.has_args("git", "clone")
    assert config.activate_script.is_file()
    assert config.activate_fish.is_file()
    assert not (tmp_path / ".bashrc").exists()


def test_run_setup_skip_one_python_tool(tmp_path: Path) -> None:
    host = FakeHost(tmp_path)
    esptool_only = make_config(
        tmp_path / "a",
        skip_platformio=True,
        skip_packages=True,
        skip_idf=True,
        skip_udev=True,
        skip_dialout=True,
    )
    runner = FakeRunner()
    run_setup(esptool_only, runner, host)
    assert any(ESPTOOL_SPEC in " ".join(call["args"]) for call in runner.calls)  # type: ignore[arg-type]
    assert not any(PLATFORMIO_SPEC in " ".join(call["args"]) for call in runner.calls)  # type: ignore[arg-type]

    pio_only = make_config(
        tmp_path / "b",
        skip_esptool=True,
        skip_packages=True,
        skip_idf=True,
        skip_udev=True,
        skip_dialout=True,
    )
    pio_runner = FakeRunner()
    run_setup(pio_only, pio_runner, host)
    assert any(PLATFORMIO_SPEC in " ".join(call["args"]) for call in pio_runner.calls)  # type: ignore[arg-type]
    assert not any(ESPTOOL_SPEC in " ".join(call["args"]) for call in pio_runner.calls)  # type: ignore[arg-type]


def test_run_setup_dry_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = make_config(
        tmp_path,
        dry_run=True,
        skip_packages=True,
        skip_esptool=True,
        skip_platformio=True,
        skip_idf=True,
        skip_udev=True,
        skip_dialout=True,
    )
    run_setup(config, FakeRunner(dry_run=True), FakeHost(tmp_path))
    captured = capsys.readouterr()
    assert "Dry run complete" in captured.out
    assert not config.activate_script.exists()
    assert not (tmp_path / ".bashrc").exists()
