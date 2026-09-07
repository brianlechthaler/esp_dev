"""Tests for the agent-skill installer."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from esp32_dev.skill_install import (
    AGENT_DEFS,
    InstallOptions,
    SkillInstallError,
    agent_by_id,
    all_agent_ids,
    build_parser,
    command_on_path,
    confirm,
    console_entry,
    default_repo_root,
    detect_agents,
    discover_skills,
    expand_agents,
    expand_home,
    expand_skills,
    expand_uninstall_skills,
    install_skill_for_agent,
    list_agents,
    list_skills,
    main,
    make_executable_sh_files,
    remove_destination,
    resolve_agent_dir,
    run_install,
    run_uninstall,
    uninstall_skill_for_agent,
    validate_agent_id,
    validate_skill_name,
)


def _write_skill(root: Path, name: str = "esp32-dev") -> Path:
    skill_dir = root / name
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: test skill\n---\n# {name}\n",
        encoding="utf-8",
    )
    script = skill_dir / "scripts" / "run.sh"
    script.parent.mkdir()
    script.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    return skill_dir


def _options(tmp_path: Path, **kwargs: object) -> InstallOptions:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_skill(repo)
    values: dict[str, object] = {
        "repo_root": repo,
        "project_dir": tmp_path / "project",
        "home_dir": tmp_path / "home",
        "yes": True,
    }
    values.update(kwargs)
    return InstallOptions(**values)  # type: ignore[arg-type]


def test_discover_skills_finds_skill_directories(tmp_path: Path) -> None:
    _write_skill(tmp_path)
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "SKILL.md").write_text("# x\n", encoding="utf-8")
    (tmp_path / "empty").mkdir()
    (tmp_path / "file.txt").write_text("x", encoding="utf-8")
    assert discover_skills(tmp_path) == ["esp32-dev"]
    assert discover_skills(tmp_path / "missing") == []


def test_discover_skills_skips_unreadable_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_is_dir = Path.is_dir

    def boom(self: Path) -> bool:
        if self == tmp_path:
            raise OSError("denied")
        return original_is_dir(self)

    monkeypatch.setattr(Path, "is_dir", boom)
    assert discover_skills(tmp_path) == []


def test_discover_skills_skips_unreadable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_self: Path) -> list[Path]:
        raise OSError("denied")

    monkeypatch.setattr(Path, "iterdir", boom)
    assert discover_skills(tmp_path) == []


def test_discover_skills_skips_unreadable_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_skill(tmp_path)
    original_is_dir = Path.is_dir

    def maybe_denied(self: Path) -> bool:
        if self.name == "esp32-dev":
            raise OSError("denied")
        return original_is_dir(self)

    monkeypatch.setattr(Path, "is_dir", maybe_denied)
    assert discover_skills(tmp_path) == []


def test_validate_skill_name_rejects_invalid() -> None:
    validate_skill_name("esp32-dev")
    with pytest.raises(SkillInstallError, match="invalid skill name"):
        validate_skill_name("ESP32")
    with pytest.raises(SkillInstallError, match="invalid skill name"):
        validate_skill_name("../evil")


def test_agent_lookup_and_ids() -> None:
    cursor = agent_by_id("cursor")
    assert cursor is not None
    assert cursor.project == ".cursor/skills"
    assert cursor.global_path == "~/.cursor/skills"
    assert agent_by_id("nope") is None
    assert "cursor" in all_agent_ids()
    assert len(all_agent_ids()) == len(AGENT_DEFS)


def test_validate_agent_id() -> None:
    validate_agent_id("cursor")
    validate_agent_id("all")
    with pytest.raises(SkillInstallError, match="unknown agent"):
        validate_agent_id("nope")


def test_expand_home(tmp_path: Path) -> None:
    assert expand_home("~/skills", tmp_path) == tmp_path / "skills"
    assert expand_home("/abs/path", tmp_path) == Path("/abs/path")


def test_resolve_agent_dir_global_and_project(tmp_path: Path) -> None:
    options = _options(tmp_path, global_install=False)
    local = resolve_agent_dir(options, "cursor")
    assert local == options.project_dir / ".cursor/skills"
    options.global_install = True
    glob = resolve_agent_dir(options, "cursor")
    assert glob == options.home_dir / ".cursor/skills"
    with pytest.raises(SkillInstallError, match="unknown agent"):
        resolve_agent_dir(options, "nope")


def test_list_skills_and_agents(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_skill(repo)
    assert list_skills(repo) == ["esp32-dev"]
    with pytest.raises(SkillInstallError, match="no skills found"):
        list_skills(tmp_path / "empty")
    list_agents()
    out = capsys.readouterr().out
    assert "cursor" in out
    assert "~/.cursor/skills" in out


def test_command_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("esp32_dev.skill_install.shutil.which", lambda name: "/bin/cursor")
    assert command_on_path("cursor") is True
    monkeypatch.setattr("esp32_dev.skill_install.shutil.which", lambda name: None)
    assert command_on_path("cursor") is False


def test_detect_agents_from_home_and_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    (home / ".cursor").mkdir(parents=True)
    monkeypatch.setattr("esp32_dev.skill_install.shutil.which", lambda name: None)
    assert detect_agents(home) == ["cursor"]

    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(
        "esp32_dev.skill_install.shutil.which",
        lambda name: "/usr/bin/claude" if name == "claude" else None,
    )
    assert "claude-code" in detect_agents(empty)

    monkeypatch.setattr("esp32_dev.skill_install.shutil.which", lambda name: None)
    assert detect_agents(empty) == ["cursor", "claude-code", "opencode"]


def test_expand_agents_and_skills(tmp_path: Path) -> None:
    options = _options(tmp_path, skills=[], install_all_skills=True)
    assert expand_skills(options) == ["esp32-dev"]
    options.install_all_skills = False
    options.skills = ["esp32-dev"]
    assert expand_skills(options) == ["esp32-dev"]
    options.skills = ["missing"]
    with pytest.raises(SkillInstallError, match="unknown skill"):
        expand_skills(options)
    assert expand_agents(["all"]) == all_agent_ids()
    assert expand_agents(["cursor"]) == ["cursor"]
    with pytest.raises(SkillInstallError, match="unknown agent"):
        expand_agents(["nope"])


def test_expand_uninstall_skills(tmp_path: Path) -> None:
    options = _options(tmp_path, install_all_skills=True)
    assert expand_uninstall_skills(options) == ["esp32-dev"]
    options.install_all_skills = False
    options.skills = ["esp32-dev"]
    assert expand_uninstall_skills(options) == ["esp32-dev"]
    options.skills = []
    with pytest.raises(SkillInstallError, match="specify skill"):
        expand_uninstall_skills(options)
    options.skills = ["Not Valid"]
    with pytest.raises(SkillInstallError, match="invalid skill name"):
        expand_uninstall_skills(options)


def test_remove_destination_variants(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    remove_destination(missing)
    file_path = tmp_path / "file"
    file_path.write_text("x", encoding="utf-8")
    remove_destination(file_path)
    assert not file_path.exists()
    directory = tmp_path / "dir"
    directory.mkdir()
    (directory / "inner").write_text("x", encoding="utf-8")
    remove_destination(directory)
    assert not directory.exists()
    target = tmp_path / "target"
    target.write_text("x", encoding="utf-8")
    link = tmp_path / "link"
    link.symlink_to(target)
    remove_destination(link)
    assert not link.exists()
    assert target.exists()


def test_make_executable_sh_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script = tmp_path / "run.sh"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    script.chmod(0o644)
    named_dir = tmp_path / "hooks.sh"
    named_dir.mkdir()
    make_executable_sh_files(tmp_path)
    assert os.access(script, os.X_OK)
    monkeypatch.setattr("esp32_dev.skill_install.os.name", "nt")
    other = tmp_path / "skip.sh"
    other.write_text("#!/bin/sh\n", encoding="utf-8")
    other.chmod(0o644)
    make_executable_sh_files(tmp_path)
    assert not os.access(other, os.X_OK)


def test_install_and_uninstall_symlink(tmp_path: Path) -> None:
    options = _options(tmp_path, method="symlink")
    install_skill_for_agent(options, "esp32-dev", "cursor")
    dest = options.project_dir / ".cursor/skills/esp32-dev"
    assert dest.is_symlink()
    assert (dest / "SKILL.md").is_file()
    assert os.access(dest / "scripts" / "run.sh", os.X_OK)
    assert uninstall_skill_for_agent(options, "esp32-dev", "cursor") is True
    assert not dest.exists()
    assert uninstall_skill_for_agent(options, "esp32-dev", "cursor") is False


def test_install_copy_replaces_existing(tmp_path: Path) -> None:
    options = _options(tmp_path, method="copy")
    dest = options.project_dir / ".cursor/skills/esp32-dev"
    dest.mkdir(parents=True)
    (dest / "SKILL.md").write_text("old", encoding="utf-8")
    install_skill_for_agent(options, "esp32-dev", "cursor")
    assert dest.is_dir()
    assert not dest.is_symlink()
    assert "test skill" in (dest / "SKILL.md").read_text(encoding="utf-8")


def test_install_symlink_falls_back_to_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    options = _options(tmp_path, method="symlink")

    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("no symlink")

    monkeypatch.setattr(Path, "symlink_to", boom)
    install_skill_for_agent(options, "esp32-dev", "cursor")
    dest = options.project_dir / ".cursor/skills/esp32-dev"
    assert dest.is_dir()
    assert not dest.is_symlink()
    assert (dest / "SKILL.md").is_file()


def test_install_missing_source(tmp_path: Path) -> None:
    options = _options(tmp_path)
    with pytest.raises(SkillInstallError, match="missing skill source"):
        install_skill_for_agent(options, "nope", "cursor")


def test_uninstall_skips_non_skill_directory(tmp_path: Path) -> None:
    options = _options(tmp_path)
    dest = options.project_dir / ".cursor/skills/esp32-dev"
    dest.mkdir(parents=True)
    (dest / "README.md").write_text("not a skill", encoding="utf-8")
    assert uninstall_skill_for_agent(options, "esp32-dev", "cursor") is False
    assert dest.exists()


def test_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    assert confirm("go?", yes=True) is True
    monkeypatch.setattr("builtins.input", lambda _prompt: "y")
    assert confirm("go?", yes=False) is True
    monkeypatch.setattr("builtins.input", lambda _prompt: "no")
    assert confirm("go?", yes=False) is False


def test_run_install_and_uninstall(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    options = _options(tmp_path, agents=["cursor"], install_all_skills=True)
    assert run_install(options) == 0
    dest = options.project_dir / ".cursor/skills/esp32-dev"
    assert dest.exists()
    out = capsys.readouterr().out
    assert "esp32-dev" in out
    options.uninstall = True
    assert run_uninstall(options) == 0
    assert not dest.exists()
    assert "removed" in capsys.readouterr().out.lower()
    assert run_uninstall(options) == 0
    assert "not installed" in capsys.readouterr().out


def test_run_install_auto_detects_agents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    options = _options(tmp_path, agents=[], install_all_skills=True)
    (options.home_dir / ".cursor").mkdir(parents=True)
    monkeypatch.setattr("esp32_dev.skill_install.shutil.which", lambda name: None)
    assert run_install(options) == 0
    assert "auto-detected" in capsys.readouterr().out
    assert (options.project_dir / ".cursor/skills/esp32-dev").exists()


def test_run_install_and_uninstall_cancel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    options = _options(tmp_path, agents=["cursor"], yes=False, install_all_skills=True)
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")
    assert run_install(options) == 0
    assert "cancelled" in capsys.readouterr().out
    assert not (options.project_dir / ".cursor/skills/esp32-dev").exists()
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")
    assert run_uninstall(options) == 0
    assert "cancelled" in capsys.readouterr().out


def test_build_parser_flags() -> None:
    parser = build_parser()
    args = parser.parse_args(["-g", "--copy", "-a", "cursor", "-s", "esp32-dev", "-y"])
    assert args.global_install is True
    assert args.copy is True
    assert args.agents == ["cursor"]
    assert args.skills == ["esp32-dev"]
    assert args.yes is True


def test_main_list_and_list_agents(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_skill(repo)
    assert (
        main(
            ["--list"],
            repo_root=repo,
            project_dir=tmp_path / "project",
            home_dir=tmp_path / "home",
        )
        == 0
    )
    assert "esp32-dev" in capsys.readouterr().out
    assert main(["--list-agents"]) == 0
    assert "AGENT" in capsys.readouterr().out


def test_main_install_global_copy_and_uninstall(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_skill(repo)
    home = tmp_path / "home"
    project = tmp_path / "project"
    assert (
        main(
            ["-g", "--copy", "-a", "cursor", "-y"],
            repo_root=repo,
            project_dir=project,
            home_dir=home,
        )
        == 0
    )
    dest = home / ".cursor/skills/esp32-dev"
    assert dest.is_dir()
    assert not dest.is_symlink()
    assert (
        main(
            ["--uninstall", "-g", "-a", "cursor", "-y", "--all"],
            repo_root=repo,
            project_dir=project,
            home_dir=home,
        )
        == 0
    )
    assert not dest.exists()


def test_main_errors(tmp_path: Path) -> None:
    missing = tmp_path / "missing-root"
    assert main(["--list"], repo_root=missing) == 1
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_skill(repo)
    assert (
        main(
            ["-a", "nope", "-y"],
            repo_root=repo,
            project_dir=tmp_path / "project",
            home_dir=tmp_path / "home",
        )
        == 1
    )
    assert (
        main(
            ["--uninstall", "-a", "cursor", "-y"],
            repo_root=repo,
            project_dir=tmp_path / "project",
            home_dir=tmp_path / "home",
        )
        == 1
    )


def test_main_uses_env_and_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_skill(repo)
    project = tmp_path / "project"
    project.mkdir()
    home = tmp_path / "home"
    monkeypatch.setenv("SKILLS_REPO_ROOT", str(repo))
    monkeypatch.setattr(Path, "cwd", classmethod(lambda _cls: project))
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: home))
    monkeypatch.setattr("esp32_dev.skill_install.shutil.which", lambda name: None)
    (home / ".cursor").mkdir(parents=True)
    assert main(["-y"]) == 0
    assert (project / ".cursor/skills/esp32-dev").exists()


def test_console_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("esp32_dev.skill_install.main", lambda argv=None: 4)
    with pytest.raises(SystemExit) as exc:
        console_entry()
    assert exc.value.code == 4


def test_main_uses_sys_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["install.py", "--list-agents"])
    assert main() == 0
    assert "cursor" in capsys.readouterr().out


def test_repo_skill_is_discoverable() -> None:
    root = Path(__file__).resolve().parents[1]
    assert "esp32-dev" in discover_skills(root)


def test_default_repo_root_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("SKILLS_REPO_ROOT", str(repo))
    assert default_repo_root() == repo


def test_default_repo_root_uses_cwd_when_skills_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_skill(repo)
    monkeypatch.delenv("SKILLS_REPO_ROOT", raising=False)
    monkeypatch.chdir(repo)
    assert default_repo_root() == repo


def test_default_repo_root_walks_to_this_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SKILLS_REPO_ROOT", raising=False)
    tests_dir = Path(__file__).resolve().parent
    monkeypatch.chdir(tests_dir)
    root = default_repo_root()
    assert "esp32-dev" in discover_skills(root)


def test_default_repo_root_falls_back_to_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SKILLS_REPO_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("esp32_dev.skill_install.discover_skills", lambda _root: [])
    assert default_repo_root() == tmp_path


def test_run_install_global_scope(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    options = _options(tmp_path, agents=["cursor"], global_install=True, install_all_skills=True)
    assert run_install(options) == 0
    assert (options.home_dir / ".cursor/skills/esp32-dev").exists()
    assert "global" in capsys.readouterr().out


def test_run_uninstall_auto_detects_agents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    options = _options(tmp_path, agents=[], install_all_skills=True)
    (options.home_dir / ".cursor").mkdir(parents=True)
    monkeypatch.setattr("esp32_dev.skill_install.shutil.which", lambda name: None)
    assert run_uninstall(options) == 0
    assert "auto-detected" in capsys.readouterr().out
