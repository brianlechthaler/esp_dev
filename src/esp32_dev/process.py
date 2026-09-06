"""Host and subprocess abstractions used by the installer."""

from __future__ import annotations

import getpass
import grp
import logging
import os
import platform
import pwd
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from esp32_dev.errors import SetupError

logger = logging.getLogger("esp32_dev")


@dataclass(frozen=True)
class CommandResult:
    """Captured result of a subprocess invocation."""

    returncode: int
    stdout: str
    stderr: str


class Host(Protocol):
    """Operating-system facts the installer needs."""

    def system(self) -> str:
        """Return the OS name, e.g. ``Linux``."""

    def python_version(self) -> tuple[int, int]:
        """Return the major and minor Python version."""

    def python_executable(self) -> str:
        """Return the path to the running Python interpreter."""

    def euid(self) -> int:
        """Return the effective user id."""

    def user_gid(self) -> int:
        """Return the current user's primary group id."""

    def username(self) -> str:
        """Return the current login name."""

    def home(self) -> Path:
        """Return the current user's home directory."""

    def os_release_path(self) -> Path:
        """Return the path to ``/etc/os-release``."""

    def group_members(self, name: str) -> tuple[int, list[str]] | None:
        """Return ``(gid, member names)`` for a group, or ``None`` if missing."""

    def is_root(self) -> bool:
        """Return whether the process is running as root."""

    def shell(self) -> str:
        """Return the user's login shell path."""


class Runner(Protocol):
    """Command execution used by install steps."""

    dry_run: bool
    use_sudo: bool

    def run(
        self,
        args: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        check: bool = True,
        mutate: bool = False,
        stdin: str | None = None,
        sudo: bool = False,
        timeout: float | None = None,
        stream: bool = False,
    ) -> CommandResult:
        """Run ``args`` and return captured output."""

    def which(self, name: str) -> str | None:
        """Return the path to an executable, or ``None`` if it is not on PATH."""


class SystemHost:
    """Host implementation backed by the current process and OS."""

    def system(self) -> str:
        return platform.system()

    def python_version(self) -> tuple[int, int]:
        return sys.version_info[0], sys.version_info[1]

    def python_executable(self) -> str:
        return sys.executable

    def euid(self) -> int:
        return os.geteuid()

    def user_gid(self) -> int:
        return os.getgid()

    def username(self) -> str:
        return getpass.getuser()

    def home(self) -> Path:
        return Path.home()

    def os_release_path(self) -> Path:
        return Path("/etc/os-release")

    def group_members(self, name: str) -> tuple[int, list[str]] | None:
        try:
            group = grp.getgrnam(name)
        except KeyError:
            return None
        return group.gr_gid, list(group.gr_mem)

    def is_root(self) -> bool:
        return self.euid() == 0

    def shell(self) -> str:
        env = os.environ.get("SHELL")
        if env:
            return env
        try:
            return pwd.getpwuid(os.getuid()).pw_shell
        except (KeyError, OSError):
            return "/bin/sh"


class CommandRunner:
    """Subprocess runner with optional dry-run and sudo wrapping."""

    def __init__(self, host: Host, *, dry_run: bool = False, use_sudo: bool = True) -> None:
        self.host = host
        self.dry_run = dry_run
        self.use_sudo = use_sudo

    def which(self, name: str) -> str | None:
        return shutil.which(name)

    def run(
        self,
        args: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        check: bool = True,
        mutate: bool = False,
        stdin: str | None = None,
        sudo: bool = False,
        timeout: float | None = None,
        stream: bool = False,
    ) -> CommandResult:
        if not args:
            raise SetupError("command must not be empty")
        cmd = [str(part) for part in args]
        if sudo and self.use_sudo and not self.host.is_root():
            cmd = ["sudo", *cmd]
        rendered = " ".join(cmd)
        if self.dry_run and mutate:
            logger.info("dry-run: %s", rendered)
            return CommandResult(0, "", "")
        logger.debug("run: %s", rendered)
        try:
            if stream:
                completed = subprocess.run(
                    cmd,
                    cwd=cwd,
                    env=dict(env) if env is not None else None,
                    input=stdin,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
            else:
                completed = subprocess.run(
                    cmd,
                    cwd=cwd,
                    env=dict(env) if env is not None else None,
                    input=stdin,
                    text=True,
                    capture_output=True,
                    timeout=timeout,
                    check=False,
                )
        except FileNotFoundError as exc:
            raise SetupError(f"command not found: {cmd[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise SetupError(f"command timed out: {rendered}") from exc
        result = CommandResult(
            completed.returncode,
            completed.stdout or "",
            completed.stderr or "",
        )
        if check and result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
            raise SetupError(f"command failed ({result.returncode}): {rendered}\n{detail}")
        return result
