# Agent skill

Installs the **esp32-dev** agent skill so coding tools reuse the shared ESP32 toolkit (`pio`, `idf.py`, esptool) at `~/.esp32-dev` instead of downloading those toolchains again.

## Overview

The skill lives in `esp32-dev/SKILL.md`. The installer is `install.py` at the repo root (same flag style as [brianlechthaler/skills](https://github.com/brianlechthaler/skills): project-local vs `-g` global, symlink vs `--copy`, `-a` agent, `--uninstall`).

Default skill install is a **symlink** into the agent skills directory so edits in this clone are picked up. Use `--copy` when the clone will be removed.

## Usage

From this repository:

```bash
python3 install.py --list
python3 install.py --list-agents
python3 install.py -a cursor -y                 # this project: .cursor/skills/esp32-dev
python3 install.py -g -a cursor -y              # user-wide: ~/.cursor/skills/esp32-dev
python3 install.py -g -a cursor --copy -y       # copy instead of symlink
python3 install.py --uninstall -g -a cursor -y --all
```

`-a all` installs to every supported agent path. If `-a` is omitted, the installer auto-detects tools (Cursor, Claude Code, and others) from home directories and `PATH`.

Restart the coding tool (or start a new agent session) after install.

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `-g`, `--global` | project-local | Install under the user home dir |
| `-a`, `--agent` | auto-detect | Target tool (`cursor`, `claude-code`, …, or `all`) |
| `--copy` | symlink | Copy the skill directory |
| `--uninstall` | off | Remove an installed skill |
| `--all` | install: all skills in the repo | Required with `--uninstall` unless `-s` is set |
| `-y`, `--yes` | prompt | Skip confirmation |
| `SKILLS_REPO_ROOT` | discovered from cwd / this repo | Override the skill source root |

## After install

Agents that load the skill should:

1. Source `~/.esp32-dev/activate.sh` (or `$ESP32_DEV_PREFIX/activate.sh`)
2. Run `pio`, `idf.py`, and `python -m esptool` from that environment
3. If the prefix is missing, run this repo's `./scripts/setup-esp32-dev.sh` (or `python3 -m esp32_dev setup`) once — not a parallel pip/git toolchain

Helper: `esp32-dev/scripts/with-env.sh <command>`.

## Troubleshooting

**`no skills found`** — run `install.py` from a clone of this repo, or set `SKILLS_REPO_ROOT`.

**Symlink fails** — the installer falls back to copy. Pass `--copy` to skip the symlink attempt.

**Skill installed but agent still pip-installs pio** — restart the session; confirm the skill path for that tool with `python3 install.py --list-agents`.

## Related

- [Getting started](../getting-started.md)
- [README](../../README.md)
