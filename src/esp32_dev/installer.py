"""Install ESP-IDF, PlatformIO, esptool, and related host dependencies."""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from esp32_dev.config import (
    DIALOUT_GROUP,
    ESPTOOL_SPEC,
    MIN_PYTHON,
    PARTIAL_SUFFIX,
    PLATFORMIO_SPEC,
    UDEV_RULES,
    SetupConfig,
)
from esp32_dev.detect import (
    FAMILY_DEBIAN,
    FAMILY_FEDORA,
    detect_family,
    packages_for,
    read_os_release,
)
from esp32_dev.errors import SetupError
from esp32_dev.process import Host, Runner
from esp32_dev.releases import resolve_idf_version
from esp32_dev.shell import generate_activate_fish, generate_activate_script, install_shell_hooks

logger = logging.getLogger("esp32_dev")

REQUIRED_VERIFY = ("git", "python3", "esptool", "platformio", "esp-idf")


@dataclass(frozen=True)
class ToolStatus:
    """Installation status of a single tool or prerequisite."""

    name: str
    ok: bool
    detail: str


def ensure_linux(host: Host) -> None:
    """Require a Linux host."""
    system = host.system()
    if system != "Linux":
        raise SetupError(f"unsupported OS: {system} (Linux is required)")


def ensure_python(host: Host) -> None:
    """Require a supported Python version."""
    version = host.python_version()
    if version < MIN_PYTHON:
        raise SetupError(
            f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required; found {version[0]}.{version[1]}"
        )


def user_in_group(host: Host, group: str) -> bool:
    """Return whether the current user is in ``group``."""
    info = host.group_members(group)
    if info is None:
        return False
    gid, members = info
    if host.user_gid() == gid:
        return True
    return host.username() in members


def next_steps(config: SetupConfig) -> str:
    """Return the message shown after a successful setup."""
    activate = [
        "Activate tools in this shell:",
        f"  source {config.activate_script}",
    ]
    if not config.skip_shell:
        activate = [
            "New interactive shells will activate this environment automatically.",
            "This shell:",
            f"  source {config.activate_script}",
            f"  source {config.activate_fish}  # fish",
        ]
    return "\n".join(
        [
            "ESP32 development environment is ready.",
            "",
            *activate,
            "",
            "esptool:     python -m esptool",
            "PlatformIO:  pio --help",
            "ESP-IDF:     idf.py --help",
            "",
            "Upload a blink sketch to an attached ESP32:",
            "  python -m esp32_dev blink",
        ]
    )


def format_status(items: list[ToolStatus]) -> str:
    """Render status rows as aligned text."""
    if not items:
        return "no status items"
    width = max(len(item.name) for item in items)
    lines: list[str] = []
    for item in items:
        flag = "OK" if item.ok else "MISSING"
        lines.append(f"{item.name.ljust(width)}  {flag.ljust(7)}  {item.detail}")
    return "\n".join(lines)


def verify_ok(items: list[ToolStatus]) -> bool:
    """Return whether required tools in ``items`` are present."""
    by_name = {item.name: item for item in items}
    for name in REQUIRED_VERIFY:
        status = by_name.get(name)
        if status is None or not status.ok:
            return False
    return True


def _rmtree(path: Path, *, dry_run: bool) -> None:
    if dry_run:
        logger.info("dry-run: rmtree %s", path)
        return
    shutil.rmtree(path)


def _remove_path(path: Path, *, dry_run: bool) -> None:
    if dry_run:
        logger.info("dry-run: remove %s", path)
        return
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    shutil.rmtree(path)


def _finalize_directory(staging: Path, dest: Path, *, dry_run: bool) -> None:
    if dry_run:
        logger.info("dry-run: move %s -> %s", staging, dest)
        return
    if dest.exists() or dest.is_symlink():
        _remove_path(dest, dry_run=False)
    staging.rename(dest)


def _mkdir(path: Path, *, dry_run: bool) -> None:
    if dry_run:
        logger.info("dry-run: mkdir %s", path)
        return
    path.mkdir(parents=True, exist_ok=True)


def _write_text(path: Path, content: str, *, dry_run: bool) -> None:
    if dry_run:
        logger.info("dry-run: write %s", path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _can_write(path: Path) -> bool:
    parent = path.parent
    try:
        return os.access(parent, os.W_OK)
    except OSError:
        return False


def ensure_required_commands(config: SetupConfig, runner: Runner) -> None:
    """Ensure binaries needed by remaining setup steps are on PATH."""
    needed: list[str] = ["python3"]
    if not config.skip_idf:
        needed.extend(["git", "cmake", "ninja"])
    unique = list(dict.fromkeys(needed))
    missing = [name for name in unique if runner.which(name) is None]
    if missing:
        raise SetupError("missing required commands: " + ", ".join(missing))


def _package_installed(runner: Runner, family: str, package: str) -> bool:
    if family == FAMILY_DEBIAN:
        result = runner.run(
            ["dpkg-query", "-W", "-f=${Status}", package],
            check=False,
        )
        return "install ok installed" in result.stdout
    if family == FAMILY_FEDORA:
        result = runner.run(["rpm", "-q", package], check=False)
        return result.returncode == 0
    result = runner.run(["pacman", "-Qi", package], check=False)
    return result.returncode == 0


def _install_missing_packages(
    runner: Runner,
    family: str,
    missing: list[str],
) -> None:
    if family == FAMILY_DEBIAN:
        runner.run(["apt-get", "update"], sudo=True, mutate=True, timeout=600)
        runner.run(["apt-get", "install", "-y", *missing], sudo=True, mutate=True, timeout=600)
        return
    if family == FAMILY_FEDORA:
        installer = "dnf" if runner.which("dnf") is not None else "yum"
        runner.run([installer, "install", "-y", *missing], sudo=True, mutate=True, timeout=600)
        return
    runner.run(
        ["pacman", "-S", "--noconfirm", "--needed", *missing],
        sudo=True,
        mutate=True,
        timeout=600,
    )


def install_packages(config: SetupConfig, runner: Runner, host: Host) -> None:
    """Install distro packages required by ESP-IDF and related tools."""
    data = read_os_release(host.os_release_path())
    family = detect_family(data)
    if family is None:
        ident = data.get("ID", "unknown")
        raise SetupError(
            f"unsupported Linux distribution ({ident}); install prerequisites "
            "manually and re-run with --skip-packages. Debian/Ubuntu packages: "
            + " ".join(packages_for(FAMILY_DEBIAN))
        )
    packages = list(packages_for(family))
    if config.force:
        missing = packages
    else:
        missing = [pkg for pkg in packages if not _package_installed(runner, family, pkg)]
    if not missing:
        logger.info("system packages already installed")
        return
    logger.info("installing packages: %s", " ".join(missing))
    _install_missing_packages(runner, family, missing)


def ensure_venv(config: SetupConfig, runner: Runner, host: Host) -> Path:
    """Create the tools virtualenv and upgrade pip."""
    venv_dir = config.venv_dir
    python_path = config.venv_python
    if config.force and venv_dir.exists():
        _rmtree(venv_dir, dry_run=runner.dry_run)
    if not python_path.is_file():
        if venv_dir.exists():
            _rmtree(venv_dir, dry_run=runner.dry_run)
        _mkdir(venv_dir.parent, dry_run=runner.dry_run)
        runner.run(
            [host.python_executable(), "-m", "venv", str(venv_dir)],
            mutate=True,
        )
    if not runner.dry_run and not python_path.is_file():
        raise SetupError(f"failed to create venv python at {python_path}")
    if not runner.dry_run:
        runner.run(
            [str(python_path), "-m", "pip", "install", "--upgrade", "pip"],
            mutate=True,
            timeout=600,
        )
    return python_path


def pip_install(runner: Runner, venv_python: Path, spec: str) -> None:
    """Install a pip requirement into the tools virtualenv."""
    runner.run(
        [str(venv_python), "-m", "pip", "install", "--upgrade", spec],
        mutate=True,
        timeout=600,
    )


def install_esptool(runner: Runner, venv_python: Path) -> None:
    """Install esptool into the tools virtualenv."""
    logger.info("installing esptool")
    pip_install(runner, venv_python, ESPTOOL_SPEC)


def install_platformio(runner: Runner, venv_python: Path) -> None:
    """Install PlatformIO into the tools virtualenv."""
    logger.info("installing PlatformIO")
    pip_install(runner, venv_python, PLATFORMIO_SPEC)


def idf_clone_args(config: SetupConfig, dest: Path) -> list[str]:
    """Return ``git clone`` arguments for ESP-IDF."""
    args = ["git", "clone", "--progress", "--branch", config.idf_version]
    if config.shallow_idf:
        args.extend(["--depth", "1", "--recurse-submodules", "--shallow-submodules"])
    else:
        args.append("--recursive")
    args.extend([config.idf_repo, str(dest)])
    return args


def idf_fetch_args(config: SetupConfig) -> list[str]:
    """Return ``git fetch`` arguments for an existing ESP-IDF clone."""
    args = ["git", "fetch", "--progress"]
    if config.shallow_idf:
        args.extend(["--depth", "1"])
    args.extend(["origin", config.idf_version])
    return args


def idf_submodule_args(config: SetupConfig) -> list[str]:
    """Return ``git submodule update`` arguments for ESP-IDF."""
    args = ["git", "submodule", "update", "--init", "--recursive"]
    if config.shallow_idf:
        args.extend(["--depth", "1"])
    return args


def is_usable_idf_clone(dest: Path) -> bool:
    """Return whether ``dest`` looks like a complete enough ESP-IDF checkout to resume."""
    if not dest.is_dir():
        return False
    if not (dest / ".git").exists():
        return False
    return (dest / "install.sh").is_file() and (dest / "export.sh").is_file()


def _iter_prefix_children(prefix: Path) -> list[Path]:
    try:
        return list(prefix.iterdir())
    except OSError:
        logger.warning("unable to scan %s for leftover install files", prefix)
        return []


def cleanup_stale_install(config: SetupConfig, *, dry_run: bool) -> None:
    """Remove leftover staging dirs and incomplete trees from a killed install."""
    prefix = config.prefix
    if not prefix.exists():
        return
    for child in _iter_prefix_children(prefix):
        if child.name.endswith(PARTIAL_SUFFIX):
            logger.info("removing leftover staging path %s", child)
            _remove_path(child, dry_run=dry_run)
    if config.idf_dir.exists() and not is_usable_idf_clone(config.idf_dir):
        logger.info("removing incomplete ESP-IDF clone at %s", config.idf_dir)
        _remove_path(config.idf_dir, dry_run=dry_run)
    if config.venv_dir.exists() and not config.venv_python.is_file():
        logger.info("removing incomplete tools virtualenv at %s", config.venv_dir)
        _remove_path(config.venv_dir, dry_run=dry_run)


def _run_idf_install(config: SetupConfig, runner: Runner) -> None:
    install_script = config.idf_dir / "install.sh"
    if not runner.dry_run and not install_script.is_file():
        raise SetupError(f"ESP-IDF install script missing: {install_script}")
    targets = ",".join(config.idf_targets)
    runner.run(
        ["bash", str(install_script), targets],
        cwd=config.idf_dir,
        mutate=True,
        stream=True,
    )


def install_esp_idf(config: SetupConfig, runner: Runner) -> None:
    """Clone or resume ESP-IDF and run its install script."""
    config.idf_version = resolve_idf_version(config.idf_version)
    dest = config.idf_dir
    staging = config.idf_partial_dir
    if staging.exists() or staging.is_symlink():
        logger.info("removing leftover ESP-IDF clone directory %s", staging)
        _remove_path(staging, dry_run=runner.dry_run)
    if dest.exists() and not config.force and is_usable_idf_clone(dest):
        logger.info("resuming existing ESP-IDF clone at %s", dest)
        runner.run(idf_fetch_args(config), cwd=dest, mutate=True, stream=True)
        runner.run(["git", "checkout", config.idf_version], cwd=dest, mutate=True, stream=True)
        runner.run(idf_submodule_args(config), cwd=dest, mutate=True, stream=True)
        _run_idf_install(config, runner)
        return
    if dest.exists() or dest.is_symlink():
        logger.info("removing previous ESP-IDF directory %s", dest)
        _remove_path(dest, dry_run=runner.dry_run)
    if config.shallow_idf:
        logger.info(
            "cloning ESP-IDF %s into %s (shallow; one commit + submodules). "
            "This is still a large download and can take several minutes.",
            config.idf_version,
            dest,
        )
    else:
        logger.info(
            "cloning ESP-IDF %s into %s with full history and submodules. "
            "This can take a long time.",
            config.idf_version,
            dest,
        )
    _mkdir(dest.parent, dry_run=runner.dry_run)
    runner.run(idf_clone_args(config, staging), mutate=True, stream=True)
    _finalize_directory(staging, dest, dry_run=runner.dry_run)
    _run_idf_install(config, runner)


def _reload_udev(runner: Runner) -> None:
    udevadm = runner.which("udevadm")
    if udevadm is None:
        logger.warning("udevadm not found; reload udev rules after plugging in a board")
        return
    runner.run([udevadm, "control", "--reload-rules"], sudo=True, mutate=True, check=False)
    runner.run([udevadm, "trigger"], sudo=True, mutate=True, check=False)


def _existing_udev_text(path: Path) -> str | None:
    try:
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def install_udev(config: SetupConfig, runner: Runner) -> None:
    """Install udev rules so ESP32 USB serial devices are accessible."""
    path = config.udev_rules_path
    existing = _existing_udev_text(path)
    if existing == UDEV_RULES and not config.force:
        logger.info("udev rules already installed at %s", path)
        return
    if runner.dry_run:
        logger.info("dry-run: write udev rules to %s", path)
        return
    if _can_write(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(UDEV_RULES, encoding="utf-8")
    else:
        runner.run(["mkdir", "-p", str(path.parent)], sudo=True, mutate=True)
        runner.run(["tee", str(path)], stdin=UDEV_RULES, sudo=True, mutate=True)
    _reload_udev(runner)


def ensure_dialout(runner: Runner, host: Host) -> None:
    """Add the current user to the dialout group when needed."""
    if host.group_members(DIALOUT_GROUP) is None:
        logger.warning("group %s does not exist; skipping serial group membership", DIALOUT_GROUP)
        return
    if user_in_group(host, DIALOUT_GROUP):
        logger.info("%s already in group %s", host.username(), DIALOUT_GROUP)
        return
    runner.run(
        ["usermod", "-aG", DIALOUT_GROUP, host.username()],
        sudo=True,
        mutate=True,
    )
    logger.warning(
        "added %s to %s; log out and back in before using USB serial",
        host.username(),
        DIALOUT_GROUP,
    )


def collect_status(config: SetupConfig, runner: Runner, host: Host) -> list[ToolStatus]:
    """Collect installation status for tools and host prerequisites."""
    items: list[ToolStatus] = []
    for command in ("git", "cmake", "ninja", "python3"):
        path = runner.which(command)
        items.append(ToolStatus(command, path is not None, path or "not found"))
    venv_python = config.venv_python
    venv_ok = venv_python.is_file()
    items.append(ToolStatus("venv", venv_ok, str(venv_python) if venv_ok else "missing"))
    items.append(_module_status(runner, venv_python, "esptool", ["version"]))
    items.append(_module_status(runner, venv_python, "platformio", ["--version"]))
    export_sh = config.idf_dir / "export.sh"
    idf_py = config.idf_dir / "tools" / "idf.py"
    idf_ok = export_sh.is_file() and idf_py.is_file()
    idf_detail = str(config.idf_dir) if idf_ok else "ESP-IDF export.sh or idf.py missing"
    items.append(ToolStatus("esp-idf", idf_ok, idf_detail))
    udev_ok = config.udev_rules_path.is_file()
    items.append(
        ToolStatus(
            "udev",
            udev_ok,
            str(config.udev_rules_path) if udev_ok else "rules file missing",
        )
    )
    dialout_ok = user_in_group(host, DIALOUT_GROUP)
    items.append(
        ToolStatus(
            "dialout",
            dialout_ok,
            "user in dialout" if dialout_ok else "user not in dialout",
        )
    )
    return items


def _module_status(
    runner: Runner,
    venv_python: Path,
    module: str,
    extra: list[str],
) -> ToolStatus:
    if not venv_python.is_file():
        return ToolStatus(module, False, "venv python missing")
    result = runner.run([str(venv_python), "-m", module, *extra], check=False)
    detail = result.stdout.strip() or result.stderr.strip() or f"exit {result.returncode}"
    return ToolStatus(module, result.returncode == 0, detail)


def write_activate(config: SetupConfig, runner: Runner) -> None:
    """Write POSIX and fish environment activation scripts."""
    _write_text(config.activate_script, generate_activate_script(config), dry_run=runner.dry_run)
    _write_text(config.activate_fish, generate_activate_fish(config), dry_run=runner.dry_run)


def run_setup(config: SetupConfig, runner: Runner, host: Host) -> None:
    """Execute the selected setup steps."""
    ensure_linux(host)
    ensure_python(host)
    cleanup_stale_install(config, dry_run=runner.dry_run)
    _mkdir(config.prefix, dry_run=runner.dry_run)
    if config.skip_packages:
        logger.info("skipping system package installation")
    else:
        install_packages(config, runner, host)
    ensure_required_commands(config, runner)
    venv_python: Path | None = None
    if config.needs_venv:
        venv_python = ensure_venv(config, runner, host)
        if not config.skip_esptool:
            install_esptool(runner, venv_python)
        else:
            logger.info("skipping esptool")
        if not config.skip_platformio:
            install_platformio(runner, venv_python)
        else:
            logger.info("skipping PlatformIO")
    else:
        logger.info("skipping tools virtualenv")
    if config.skip_idf:
        logger.info("skipping ESP-IDF")
    else:
        install_esp_idf(config, runner)
    if config.skip_udev:
        logger.info("skipping udev rules")
    else:
        install_udev(config, runner)
    if config.skip_dialout:
        logger.info("skipping dialout group membership")
    else:
        ensure_dialout(runner, host)
    write_activate(config, runner)
    install_shell_hooks(config, runner, host)
    if config.dry_run:
        print("Dry run complete; no changes were made.")
        return
    print(next_steps(config))
