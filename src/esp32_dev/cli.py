"""Command-line interface for ESP32 development environment setup."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from esp32_dev import __version__
from esp32_dev.blink import run_blink
from esp32_dev.config import (
    DEFAULT_IDF_REPO,
    DEFAULT_IDF_VERSION,
    SetupConfig,
    default_prefix,
)
from esp32_dev.errors import SetupError
from esp32_dev.installer import collect_status, format_status, run_setup, verify_ok
from esp32_dev.process import CommandRunner, Host, Runner, SystemHost

logger = logging.getLogger("esp32_dev")


def build_parser() -> argparse.ArgumentParser:
    """Create the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="esp32-dev",
        description="Set up an ESP32 development environment (ESP-IDF, PlatformIO, and esptool).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    parser.add_argument("-q", "--quiet", action="store_true", help="errors only")
    subparsers = parser.add_subparsers(dest="command")
    setup = subparsers.add_parser("setup", help="Install tools and dependencies")
    _add_setup_flags(setup)
    resume = subparsers.add_parser(
        "resume",
        help="Resume setup after an interrupted install (same as setup)",
    )
    _add_setup_flags(resume)
    status = subparsers.add_parser("status", help="Show installation status")
    _add_prefix(status)
    verify = subparsers.add_parser("verify", help="Exit non-zero if required tools are missing")
    _add_prefix(verify)
    blink = subparsers.add_parser(
        "blink",
        help="Upload a LED blink sketch to an attached ESP32",
    )
    _add_prefix(blink)
    blink.add_argument(
        "--port",
        default=None,
        help="Serial port (default: auto-detect /dev/ttyUSB* or /dev/ttyACM*)",
    )
    blink.add_argument(
        "--board",
        default=None,
        help="PlatformIO board id (default: auto-detect from the attached chip)",
    )
    blink.add_argument(
        "--pin",
        type=int,
        default=None,
        help="GPIO pin for the LED (default: auto-detect from the attached chip)",
    )
    blink.add_argument(
        "--dry-run",
        action="store_true",
        help="Check tools and print actions without compiling or uploading",
    )
    return parser


def _add_setup_flags(parser: argparse.ArgumentParser) -> None:
    _add_prefix(parser)
    parser.add_argument(
        "--idf-version",
        default=DEFAULT_IDF_VERSION,
        help="ESP-IDF git branch or tag (default: latest GitHub release)",
    )
    parser.add_argument(
        "--idf-repo",
        default=DEFAULT_IDF_REPO,
        help="ESP-IDF git repository URL",
    )
    parser.add_argument(
        "--idf-targets",
        default="esp32",
        help="Comma-separated ESP-IDF chip targets (default: esp32)",
    )
    parser.add_argument(
        "--skip-packages",
        action="store_true",
        help="Do not install distro packages",
    )
    parser.add_argument("--skip-esptool", action="store_true", help="Do not install esptool")
    parser.add_argument("--skip-platformio", action="store_true", help="Do not install PlatformIO")
    parser.add_argument("--skip-idf", action="store_true", help="Do not install ESP-IDF")
    parser.add_argument("--skip-udev", action="store_true", help="Do not install udev rules")
    parser.add_argument(
        "--skip-dialout",
        action="store_true",
        help="Do not add the user to the dialout group",
    )
    parser.add_argument("--no-sudo", action="store_true", help="Never prefix commands with sudo")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log actions without changing the system",
    )
    parser.add_argument("--force", action="store_true", help="Reinstall components even if present")
    parser.add_argument(
        "--full-idf-clone",
        action="store_true",
        help="Clone full ESP-IDF git history instead of a shallow clone",
    )


def _add_prefix(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--prefix",
        default=str(default_prefix()),
        help="Install prefix (default: ~/.esp32-dev)",
    )


def configure_logging(verbose: bool, quiet: bool) -> None:
    """Configure package logging for CLI output."""
    if quiet:
        level = logging.ERROR
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO
    log = logging.getLogger("esp32_dev")
    log.setLevel(level)
    log.handlers.clear()
    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    log.addHandler(handler)
    log.propagate = False


def parse_idf_targets(value: str) -> tuple[str, ...]:
    """Split a comma-separated ESP-IDF target list."""
    return tuple(part.strip() for part in value.split(",") if part.strip())


def config_from_args(args: argparse.Namespace) -> SetupConfig:
    """Build a ``SetupConfig`` from parsed setup arguments."""
    prefix = Path(args.prefix).expanduser().resolve()
    return SetupConfig(
        prefix=prefix,
        idf_version=args.idf_version,
        idf_repo=args.idf_repo,
        idf_targets=parse_idf_targets(args.idf_targets),
        skip_packages=args.skip_packages,
        skip_esptool=args.skip_esptool,
        skip_platformio=args.skip_platformio,
        skip_idf=args.skip_idf,
        skip_udev=args.skip_udev,
        skip_dialout=args.skip_dialout,
        use_sudo=not args.no_sudo,
        dry_run=args.dry_run,
        force=args.force,
        shallow_idf=not args.full_idf_clone,
    )


def prefix_from_args(args: argparse.Namespace) -> Path:
    """Resolve ``--prefix`` from status/verify arguments."""
    return Path(args.prefix).expanduser().resolve()


def main(
    argv: Sequence[str] | None = None,
    *,
    host: Host | None = None,
    runner: Runner | None = None,
) -> int:
    """CLI entry point. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.quiet and args.verbose:
        parser.error("cannot use --quiet and --verbose together")
    configure_logging(args.verbose, args.quiet)
    if not args.command:
        parser.print_help()
        return 0
    resolved_host = host if host is not None else SystemHost()
    try:
        return _dispatch(args, resolved_host, runner)
    except SetupError as exc:
        logger.error("%s", exc)
        return 1


def _dispatch(args: argparse.Namespace, host: Host, runner: Runner | None) -> int:
    if args.command in {"setup", "resume"}:
        config = config_from_args(args)
        resolved = (
            runner
            if runner is not None
            else CommandRunner(
                host,
                dry_run=config.dry_run,
                use_sudo=config.use_sudo,
            )
        )
        run_setup(config, resolved, host)
        return 0
    prefix = prefix_from_args(args)
    config = SetupConfig(prefix=prefix)
    if args.command == "blink":
        resolved = runner if runner is not None else CommandRunner(host, dry_run=args.dry_run)
        run_blink(
            config,
            resolved,
            host,
            port=args.port,
            board=args.board,
            pin=args.pin,
        )
        return 0
    resolved = runner if runner is not None else CommandRunner(host)
    items = collect_status(config, resolved, host)
    print(format_status(items))
    if args.command == "status":
        return 0
    if args.command == "verify":
        return 0 if verify_ok(items) else 1
    raise SetupError(f"unknown command: {args.command}")


def console_entry() -> None:
    """Setuptools / ``python -m`` entry that exits with ``main``'s code."""
    raise SystemExit(main())
