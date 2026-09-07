"""Install this repo's agent skill into AI coding tools (global or project-local)."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import stat
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, NoReturn

SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
Method = Literal["symlink", "copy"]


class SkillInstallError(Exception):
    """Raised when the agent-skill installer cannot proceed."""


@dataclass(frozen=True)
class AgentDef:
    """Install paths for one AI coding tool."""

    id: str
    project: str
    global_path: str


AGENT_DEFS: tuple[AgentDef, ...] = (
    AgentDef("cursor", ".cursor/skills", "~/.cursor/skills"),
    AgentDef("claude-code", ".claude/skills", "~/.claude/skills"),
    AgentDef("opencode", ".opencode/skills", "~/.config/opencode/skills"),
    AgentDef("codex", ".codex/skills", "~/.codex/skills"),
    AgentDef("windsurf", ".windsurf/skills", "~/.codeium/windsurf/skills"),
    AgentDef("github-copilot", ".github/skills", "~/.copilot/skills"),
    AgentDef("gemini-cli", ".gemini/skills", "~/.gemini/skills"),
    AgentDef("openclaw", "skills", "~/.openclaw/skills"),
    AgentDef("hermes-agent", ".hermes/skills", "~/.hermes/skills"),
    AgentDef("mistral-vibe", ".vibe/skills", "~/.vibe/skills"),
    AgentDef("aider", ".aider/skills", "~/.aider/skills"),
    AgentDef("kilo-code", ".kilo/skills", "~/.kilo/skills"),
    AgentDef("augment", ".augment/skills", "~/.augment/skills"),
    AgentDef("antigravity", ".agents/skills", "~/.gemini/antigravity/skills"),
    AgentDef("cline", ".agents/skills", "~/.agents/skills"),
    AgentDef("roo", ".roo/skills", "~/.roo/skills"),
    AgentDef("continue", ".continue/skills", "~/.continue/skills"),
    AgentDef("trae", ".trae/skills", "~/.trae/skills"),
    AgentDef("universal", ".agents/skills", "~/.agents/skills"),
)


@dataclass
class InstallOptions:
    """User-selected options for installing or removing the skill."""

    repo_root: Path
    global_install: bool = False
    method: Method = "symlink"
    yes: bool = False
    uninstall: bool = False
    skills: list[str] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)
    install_all_skills: bool = False
    project_dir: Path = field(default_factory=Path.cwd)
    home_dir: Path = field(default_factory=Path.home)


def err(message: str) -> NoReturn:
    """Print an error and abort the installer."""
    print(f"error: {message}", file=sys.stderr)
    raise SkillInstallError(message)


def info(message: str) -> None:
    """Print a progress line."""
    print(f"→ {message}")


def ok(message: str) -> None:
    """Print a success line."""
    print(f"✓ {message}")


def expand_home(path: str, home: Path) -> Path:
    """Expand a ``~/...`` path against ``home``."""
    if path.startswith("~/"):
        return home / path[2:]
    return Path(path)


def agent_by_id(agent_id: str) -> AgentDef | None:
    """Return the agent definition for ``agent_id``."""
    for agent in AGENT_DEFS:
        if agent.id == agent_id:
            return agent
    return None


def all_agent_ids() -> list[str]:
    """Return every supported agent id."""
    return [agent.id for agent in AGENT_DEFS]


def validate_skill_name(name: str) -> None:
    """Require a lowercase hyphenated skill directory name."""
    if not SKILL_NAME_RE.match(name):
        err(f"invalid skill name: {name}")


def validate_agent_id(agent_id: str) -> None:
    """Require a known agent id or ``all``."""
    if agent_id == "all":
        return
    if agent_by_id(agent_id) is None:
        err(f"unknown agent: {agent_id} (see --list-agents)")


def discover_skills(root: Path) -> list[str]:
    """Return skill directory names under ``root`` that contain ``SKILL.md``."""
    try:
        if not root.is_dir():
            return []
        entries = sorted(root.iterdir())
    except OSError:
        return []
    found: list[str] = []
    for entry in entries:
        try:
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            if (entry / "SKILL.md").is_file():
                found.append(entry.name)
        except OSError:
            continue
    return found


def default_repo_root() -> Path:
    """Locate this repository: env, then cwd, then walk up from this file."""
    env = os.environ.get("SKILLS_REPO_ROOT")
    if env:
        return Path(env)
    cwd = Path.cwd()
    if discover_skills(cwd):
        return cwd
    current = Path(__file__).resolve().parent
    while True:
        if discover_skills(current):
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return cwd


def list_skills(root: Path) -> list[str]:
    """Return discovered skills, or abort if none exist."""
    found = discover_skills(root)
    if not found:
        err(f"no skills found in {root} (expected <name>/SKILL.md directories)")
    return found


def list_agents() -> None:
    """Print supported agents and their install paths."""
    print(f"{'AGENT':<18} {'SKILL PROJECT':<28} SKILL GLOBAL")
    for agent in AGENT_DEFS:
        print(f"{agent.id:<18} {agent.project:<28} {agent.global_path}")


def resolve_agent_dir(options: InstallOptions, agent_id: str) -> Path:
    """Return the skills directory for one agent in the selected scope."""
    agent = agent_by_id(agent_id)
    if agent is None:
        err(f"unknown agent: {agent_id}")
    if options.global_install:
        return expand_home(agent.global_path, options.home_dir)
    return options.project_dir / agent.project


def command_on_path(name: str) -> bool:
    """Return whether ``name`` is an executable on ``PATH``."""
    return shutil.which(name) is not None


def detect_agents(home: Path) -> list[str]:
    """Detect installed coding tools, or return a small default set."""
    detected: list[str] = []
    checks: list[tuple[str, list[Path], str | None]] = [
        ("cursor", [home / ".cursor"], "cursor"),
        ("claude-code", [home / ".claude"], "claude"),
        ("opencode", [home / ".config/opencode"], "opencode"),
        ("codex", [home / ".codex"], "codex"),
        ("windsurf", [home / ".codeium/windsurf"], "windsurf"),
        ("github-copilot", [home / ".copilot"], None),
        ("gemini-cli", [home / ".gemini"], "gemini"),
        ("openclaw", [home / ".openclaw"], "openclaw"),
        ("hermes-agent", [home / ".hermes"], "hermes"),
        ("mistral-vibe", [home / ".vibe"], "vibe"),
        ("aider", [home / ".aider"], "aider"),
        ("kilo-code", [home / ".kilo", home / ".kilocode"], None),
        (
            "antigravity",
            [home / ".gemini/antigravity", home / ".gemini/antigravity-cli"],
            None,
        ),
    ]
    for agent_id, dirs, cmd in checks:
        if any(path.is_dir() for path in dirs) or (cmd is not None and command_on_path(cmd)):
            detected.append(agent_id)
    if not detected:
        return ["cursor", "claude-code", "opencode"]
    return detected


def expand_agents(agents: list[str]) -> list[str]:
    """Expand ``all`` and validate agent ids."""
    expanded: list[str] = []
    for agent_id in agents:
        if agent_id == "all":
            expanded.extend(all_agent_ids())
        else:
            validate_agent_id(agent_id)
            expanded.append(agent_id)
    return expanded


def expand_skills(options: InstallOptions) -> list[str]:
    """Resolve the skill list for an install."""
    available = list_skills(options.repo_root)
    if options.install_all_skills or not options.skills:
        return available
    for want in options.skills:
        validate_skill_name(want)
        if want not in available:
            err(f"unknown skill: {want} (see --list)")
    return options.skills


def expand_uninstall_skills(options: InstallOptions) -> list[str]:
    """Resolve the skill list for an uninstall."""
    if options.install_all_skills:
        return list_skills(options.repo_root)
    if not options.skills:
        err("specify skill(s) with -s/--skill or use --all to uninstall every skill")
    for want in options.skills:
        validate_skill_name(want)
    return options.skills


def make_executable_sh_files(dest: Path) -> None:
    """Mark ``*.sh`` files executable after a copy or symlink install."""
    if os.name == "nt":
        return
    for sh_file in dest.rglob("*.sh"):
        if sh_file.is_file():
            mode = sh_file.stat().st_mode
            sh_file.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def remove_destination(dest: Path) -> None:
    """Remove a previous skill install at ``dest``."""
    if not dest.exists() and not dest.is_symlink():
        return
    if dest.is_symlink():
        dest.unlink()
        return
    if dest.is_dir():
        info(f"replacing existing {dest}")
        shutil.rmtree(dest)
        return
    dest.unlink()


def install_skill_for_agent(options: InstallOptions, skill: str, agent_id: str) -> None:
    """Symlink or copy one skill into one agent's skills directory."""
    validate_skill_name(skill)
    src = options.repo_root / skill
    skill_file = src / "SKILL.md"
    if not skill_file.is_file():
        err(f"missing skill source: {src}")
    agent_dir = resolve_agent_dir(options, agent_id)
    dest = agent_dir / skill
    agent_dir.mkdir(parents=True, exist_ok=True)
    remove_destination(dest)
    if options.method == "copy":
        shutil.copytree(src, dest)
    else:
        try:
            dest.symlink_to(src.resolve())
        except OSError as exc:
            info(f"symlink failed, using copy: {exc}")
            shutil.copytree(src, dest)
    make_executable_sh_files(dest)
    ok(f"{skill} -> {dest} ({agent_id})")


def uninstall_skill_for_agent(options: InstallOptions, skill: str, agent_id: str) -> bool:
    """Remove one installed skill directory or symlink. Return whether it existed."""
    validate_skill_name(skill)
    agent_dir = resolve_agent_dir(options, agent_id)
    dest = agent_dir / skill
    if not dest.exists() and not dest.is_symlink():
        info(f"{skill} not installed ({agent_id})")
        return False
    if dest.is_dir() and not dest.is_symlink() and not (dest / "SKILL.md").is_file():
        info(f"skipping {dest} (not a skill directory)")
        return False
    remove_destination(dest)
    ok(f"removed {skill} from {agent_dir} ({agent_id})")
    return True


def confirm(prompt: str, yes: bool) -> bool:
    """Return whether the user confirmed, or ``True`` when ``yes`` is set."""
    if yes:
        return True
    reply = input(f"{prompt} [y/N] ").strip()
    return reply.lower() in {"y", "yes"}


def build_parser() -> argparse.ArgumentParser:
    """Create the skill-installer argument parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Install the ESP32 dest toolkit agent skill into AI coding tools "
            "(Cursor and others). Use -g for a user-wide install, or omit it "
            "to install into the current project."
        ),
    )
    parser.add_argument("--list", action="store_true", help="List skills in this repo")
    parser.add_argument(
        "--list-agents",
        action="store_true",
        help="List supported agents and install paths",
    )
    parser.add_argument(
        "-s",
        "--skill",
        action="append",
        default=[],
        dest="skills",
        help="Install skill(s)",
    )
    parser.add_argument("--all", action="store_true", dest="install_all", help="Install all skills")
    parser.add_argument(
        "-a",
        "--agent",
        action="append",
        default=[],
        dest="agents",
        help="Target agent(s)",
    )
    parser.add_argument(
        "-g",
        "--global",
        action="store_true",
        dest="global_install",
        help="Install to home dirs",
    )
    parser.add_argument("--copy", action="store_true", help="Copy files instead of symlinking")
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove installed skill(s) instead of installing",
    )
    parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompts")
    parser.add_argument("positional_skills", nargs="*", help="Skill names")
    return parser


def _print_plan(options: InstallOptions, skills: list[str], agents: list[str]) -> None:
    scope = (
        f"global ({options.home_dir})"
        if options.global_install
        else f"project ({options.project_dir})"
    )
    print()
    print(f"Skills : {' '.join(skills)}")
    print(f"Agents : {' '.join(agents)}")
    print(f"Scope : {scope}")
    if not options.uninstall:
        print(f"Method : {options.method}")
    print()


def run_install(options: InstallOptions) -> int:
    """Install selected skills into selected agents."""
    skills = expand_skills(options)
    agents = options.agents or detect_agents(options.home_dir)
    if not options.agents:
        info(f"auto-detected agents: {' '.join(agents)}")
    agents = expand_agents(agents)
    _print_plan(options, skills, agents)
    if not confirm("Proceed with installation?", options.yes):
        print("cancelled.")
        return 0
    for agent_id in agents:
        for skill in skills:
            install_skill_for_agent(options, skill, agent_id)
    print()
    ok(f"installed {len(skills)} skill(s) to {len(agents)} agent(s).")
    print("Restart your coding tool or start a new session to pick up changes.")
    return 0


def run_uninstall(options: InstallOptions) -> int:
    """Remove selected skills from selected agents."""
    skills = expand_uninstall_skills(options)
    agents = options.agents or detect_agents(options.home_dir)
    if not options.agents:
        info(f"auto-detected agents: {' '.join(agents)}")
    agents = expand_agents(agents)
    _print_plan(options, skills, agents)
    if not confirm("Proceed with uninstall?", options.yes):
        print("cancelled.")
        return 0
    removed = 0
    for agent_id in agents:
        for skill in skills:
            if uninstall_skill_for_agent(options, skill, agent_id):
                removed += 1
    print()
    ok(f"removed {removed} skill(s) from {len(agents)} agent(s).")
    print("Restart your coding tool or start a new session to pick up changes.")
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    repo_root: Path | None = None,
    project_dir: Path | None = None,
    home_dir: Path | None = None,
) -> int:
    """CLI entry point. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        return _dispatch(
            args,
            repo_root=repo_root,
            project_dir=project_dir,
            home_dir=home_dir,
        )
    except SkillInstallError:
        return 1


def _dispatch(
    args: argparse.Namespace,
    *,
    repo_root: Path | None,
    project_dir: Path | None,
    home_dir: Path | None,
) -> int:
    if args.list_agents:
        list_agents()
        return 0
    resolved_root = repo_root if repo_root is not None else default_repo_root()
    needs_repo = not args.uninstall or args.install_all or args.list
    if needs_repo and not resolved_root.is_dir():
        err(f"repo root not found: {resolved_root}")
    options = InstallOptions(
        repo_root=resolved_root,
        global_install=args.global_install,
        method="copy" if args.copy else "symlink",
        yes=args.yes,
        uninstall=args.uninstall,
        skills=[*args.skills, *args.positional_skills],
        agents=args.agents,
        install_all_skills=args.install_all,
        project_dir=project_dir if project_dir is not None else Path.cwd(),
        home_dir=home_dir if home_dir is not None else Path.home(),
    )
    if args.uninstall:
        return run_uninstall(options)
    if args.list:
        for skill in list_skills(options.repo_root):
            print(skill)
        return 0
    return run_install(options)


def console_entry() -> None:
    """Setuptools-style entry that exits with ``main``'s code."""
    raise SystemExit(main())
