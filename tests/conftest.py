"""Shared test doubles for ESP32 setup tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from esp32_dev.config import SetupConfig
from esp32_dev.errors import SetupError
from esp32_dev.process import CommandResult


@dataclass
class FakeHost:
    """In-memory host used by installer tests."""

    tmp_path: Path
    system_name: str = "Linux"
    version: tuple[int, int] = (3, 13)
    executable: str = "/usr/bin/python3"
    euid_value: int = 1000
    gid_value: int = 1000
    user: str = "tester"
    groups: dict[str, tuple[int, list[str]]] = field(
        default_factory=lambda: {"dialout": (20, ["tester"])}
    )
    os_release: str = "ID=debian\nID_LIKE=debian\n"
    shell_path: str = "/bin/bash"

    def __post_init__(self) -> None:
        self._os_release_path = self.tmp_path / "os-release"
        self._os_release_path.write_text(self.os_release, encoding="utf-8")

    def system(self) -> str:
        return self.system_name

    def python_version(self) -> tuple[int, int]:
        return self.version

    def python_executable(self) -> str:
        return self.executable

    def euid(self) -> int:
        return self.euid_value

    def user_gid(self) -> int:
        return self.gid_value

    def username(self) -> str:
        return self.user

    def home(self) -> Path:
        return self.tmp_path

    def os_release_path(self) -> Path:
        return self._os_release_path

    def group_members(self, name: str) -> tuple[int, list[str]] | None:
        return self.groups.get(name)

    def is_root(self) -> bool:
        return self.euid() == 0

    def shell(self) -> str:
        return self.shell_path


class FakeRunner:
    """Records commands and optionally creates venv/IDF files."""

    def __init__(
        self,
        *,
        dry_run: bool = False,
        use_sudo: bool = True,
        apply_side_effects: bool = True,
    ) -> None:
        self.dry_run = dry_run
        self.use_sudo = use_sudo
        self.apply_side_effects = apply_side_effects
        self.calls: list[dict[str, object]] = []
        self.which_map: dict[str, str | None] = {
            "python3": "/usr/bin/python3",
            "git": "/usr/bin/git",
            "cmake": "/usr/bin/cmake",
            "ninja": "/usr/bin/ninja",
            "dnf": "/usr/bin/dnf",
            "udevadm": "/usr/bin/udevadm",
        }
        self.results: dict[tuple[str, ...], CommandResult] = {}
        self.missing_packages: set[str] = set()
        self.module_versions: dict[str, CommandResult] = {
            "esptool": CommandResult(0, "esptool.py v4.8.1", ""),
            "platformio": CommandResult(0, "PlatformIO Core, version 6.1.16", ""),
        }
        self.chip_id_result = CommandResult(0, "Chip type:          ESP32 (revision v3.0)\n", "")
        self.console_result: CommandResult | None = None

    def which(self, name: str) -> str | None:
        return self.which_map.get(name)

    def run(
        self,
        args: list[str] | tuple[str, ...],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        check: bool = True,
        mutate: bool = False,
        stdin: str | None = None,
        sudo: bool = False,
        timeout: float | None = None,
        stream: bool = False,
    ) -> CommandResult:
        cmd = [str(part) for part in args]
        self.calls.append(
            {
                "args": cmd,
                "cwd": cwd,
                "env": env,
                "check": check,
                "mutate": mutate,
                "stdin": stdin,
                "sudo": sudo,
                "timeout": timeout,
                "stream": stream,
            }
        )
        if mutate and self.dry_run:
            return CommandResult(0, "", "")
        if self.apply_side_effects:
            _apply_side_effects(cmd)
        result = self._result_for(cmd)
        if check and result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
            raise SetupError(f"command failed ({result.returncode}): {' '.join(cmd)}\n{detail}")
        return result

    def _result_for(self, cmd: list[str]) -> CommandResult:
        key = tuple(cmd)
        if key in self.results:
            return self.results[key]
        if cmd and cmd[0] == "dpkg-query":
            package = cmd[-1]
            if package in self.missing_packages:
                return CommandResult(1, "", "not installed")
            return CommandResult(0, "install ok installed", "")
        if cmd[:2] == ["rpm", "-q"]:
            package = cmd[-1]
            if package in self.missing_packages:
                return CommandResult(1, "", "")
            return CommandResult(0, package, "")
        if cmd[:2] == ["pacman", "-Qi"]:
            package = cmd[-1]
            if package in self.missing_packages:
                return CommandResult(1, "", "")
            return CommandResult(0, package, "")
        if any(part in {"chip-id", "chip_id"} for part in cmd):
            return self.chip_id_result
        if len(cmd) >= 2 and cmd[1] == "-c":
            if self.console_result is not None:
                return self.console_result
            return CommandResult(0, "LED on\nLED off\n", "")
        if len(cmd) >= 3 and cmd[1] == "-m":
            module = cmd[2]
            if module in self.module_versions:
                return self.module_versions[module]
        return CommandResult(0, "ok", "")

    def has_args(self, *parts: str) -> bool:
        """Return whether any recorded command starts with ``parts``."""
        needle = list(parts)
        for call in self.calls:
            args = call["args"]
            assert isinstance(args, list)
            if args[: len(needle)] == needle:
                return True
        return False


def _apply_side_effects(cmd: list[str]) -> None:
    if len(cmd) >= 4 and cmd[-3] == "-m" and cmd[-2] == "venv":
        venv_dir = Path(cmd[-1])
        bin_dir = venv_dir / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        python_path = bin_dir / "python"
        python_path.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        python_path.chmod(0o755)
        return
    if len(cmd) >= 2 and cmd[0] == "git" and cmd[1] == "clone":
        dest = Path(cmd[-1])
        dest.mkdir(parents=True, exist_ok=True)
        (dest / ".git").mkdir(exist_ok=True)
        (dest / "tools").mkdir(exist_ok=True)
        (dest / "install.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        (dest / "export.sh").write_text("# export\n", encoding="utf-8")
        (dest / "tools" / "idf.py").write_text("# idf\n", encoding="utf-8")


def make_config(tmp_path: Path, **kwargs: object) -> SetupConfig:
    """Build a config rooted at ``tmp_path``."""
    values: dict[str, object] = {
        "prefix": tmp_path / "prefix",
        "udev_rules_path": tmp_path / "udev" / "99-esp32-dev.rules",
        "idf_version": "v6.1",
    }
    values.update(kwargs)
    return SetupConfig(**values)  # type: ignore[arg-type]
