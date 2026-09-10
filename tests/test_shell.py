"""Tests for activate scripts and shell rc-file integration."""

from __future__ import annotations

from pathlib import Path

from esp32_dev.installer import generate_activate_script, next_steps, run_setup, write_activate
from esp32_dev.shell import (
    HOOK_BEGIN,
    HOOK_END,
    generate_activate_fish,
    generate_rc_hook,
    install_shell_hooks,
    login_shell_name,
    rc_files_to_hook,
    upsert_hook,
)
from tests.conftest import FakeHost, FakeRunner, make_config


def test_login_shell_name() -> None:
    assert login_shell_name("/bin/bash") == "bash"
    assert login_shell_name("/usr/bin/zsh") == "zsh"
    assert login_shell_name("FISH") == "fish"


def test_rc_files_include_login_shell_and_existing(tmp_path: Path) -> None:
    (tmp_path / ".zshrc").write_text("# existing zsh\n", encoding="utf-8")
    fish_dir = tmp_path / ".config" / "fish"
    fish_dir.mkdir(parents=True)
    (fish_dir / "config.fish").write_text("# existing fish\n", encoding="utf-8")
    targets = rc_files_to_hook(tmp_path, "bash")
    assert tmp_path / ".bashrc" in targets
    assert tmp_path / ".zshrc" in targets
    assert fish_dir / "config.fish" in targets
    assert targets[0] == tmp_path / ".bashrc"


def test_rc_files_for_each_common_shell(tmp_path: Path) -> None:
    assert rc_files_to_hook(tmp_path, "zsh")[0] == tmp_path / ".zshrc"
    assert rc_files_to_hook(tmp_path, "fish")[0] == tmp_path / ".config" / "fish" / "config.fish"
    assert rc_files_to_hook(tmp_path, "ksh")[0] == tmp_path / ".kshrc"
    assert rc_files_to_hook(tmp_path, "mksh")[0] == tmp_path / ".kshrc"
    assert rc_files_to_hook(tmp_path, "pdksh")[0] == tmp_path / ".kshrc"
    assert rc_files_to_hook(tmp_path, "dash")[0] == tmp_path / ".profile"
    assert rc_files_to_hook(tmp_path, "sh")[0] == tmp_path / ".profile"
    assert rc_files_to_hook(tmp_path, "ash")[0] == tmp_path / ".profile"
    assert rc_files_to_hook(tmp_path, "nu") == []
    (tmp_path / ".bashrc").write_text("# existing\n", encoding="utf-8")
    assert tmp_path / ".bashrc" in rc_files_to_hook(tmp_path, "nu")


def test_generate_activate_script_is_posix_and_guarded(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    script = generate_activate_script(config)
    assert f'ESP32_DEV_PREFIX="{config.prefix}"' in script
    assert "ESP32_DEV_ACTIVE" in script
    assert "venv/bin/activate" in script
    assert "IDF_PATH" in script
    assert "CARGO_HOME" in script
    assert "RUSTUP_HOME" in script
    assert "export-esp.sh" in script
    assert "BASH_VERSION" in script
    assert "ZSH_VERSION" in script


def test_generate_activate_fish(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    script = generate_activate_fish(config)
    assert f'set -gx ESP32_DEV_PREFIX "{config.prefix}"' in script
    assert "activate.fish" in script
    assert "export.fish" in script
    assert "ESP32_DEV_ACTIVE" in script
    assert "CARGO_HOME" in script
    assert "RUSTUP_HOME" in script
    assert "$CARGO_HOME/bin" in script


def test_generate_activate_fish_converts_export_esp(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.prefix.mkdir(parents=True)
    config.export_esp_script.write_text(
        "# comment\n"
        'export LIBCLANG_PATH="/opt/esp-clang/lib"\n'
        'export PATH="/opt/esp-toolchain/bin:$PATH"\n'
        "not-an-export\n"
        "export BARE\n",
        encoding="utf-8",
    )
    script = generate_activate_fish(config)
    assert 'set -gx LIBCLANG_PATH "/opt/esp-clang/lib"' in script
    assert "set -gx PATH /opt/esp-toolchain/bin $PATH" in script
    assert "BARE" not in script
    config.export_esp_script.write_text("# none\nexport =ignored\nexport BARE\n", encoding="utf-8")
    empty = generate_activate_fish(config)
    assert "ignored" not in empty
    assert 'set -gx CARGO_HOME "$ESP32_DEV_PREFIX/cargo"' in empty


def test_generate_rc_hook_posix_is_interactive_only(tmp_path: Path) -> None:
    hook = generate_rc_hook(tmp_path / "prefix", tmp_path / ".bashrc")
    assert HOOK_BEGIN in hook
    assert HOOK_END in hook
    assert "case $-" in hook
    assert "*i*" in hook
    assert str(tmp_path / "prefix" / "activate.sh") in hook


def test_generate_rc_hook_fish_is_interactive_only(tmp_path: Path) -> None:
    hook = generate_rc_hook(tmp_path / "prefix", tmp_path / ".config" / "fish" / "config.fish")
    assert "status is-interactive" in hook
    assert "activate.fish" in hook
    assert "source" in hook


def test_upsert_hook_inserts_replaces_and_repairs(tmp_path: Path) -> None:
    path = tmp_path / ".bashrc"
    first = f"{HOOK_BEGIN}\nONE\n{HOOK_END}\n"
    upsert_hook(path, first)
    assert path.read_text(encoding="utf-8") == first
    path.write_text("keep\n", encoding="utf-8")
    upsert_hook(path, first)
    text = path.read_text(encoding="utf-8")
    assert text.startswith("keep\n")
    assert "ONE" in text
    second = f"{HOOK_BEGIN}\nTWO\n{HOOK_END}\n"
    upsert_hook(path, second)
    updated = path.read_text(encoding="utf-8")
    assert "TWO" in updated
    assert "ONE" not in updated
    assert updated.count(HOOK_BEGIN) == 1
    broken = tmp_path / ".profile"
    broken.write_text(f"head\n{HOOK_BEGIN}\norphan\n", encoding="utf-8")
    upsert_hook(broken, first)
    repaired = broken.read_text(encoding="utf-8")
    assert repaired.startswith("head\n")
    assert "ONE" in repaired
    assert "orphan" not in repaired
    assert repaired.count(HOOK_BEGIN) == 1


def test_upsert_hook_adds_newline_before_block(tmp_path: Path) -> None:
    path = tmp_path / ".kshrc"
    path.write_text("no-nl", encoding="utf-8")
    block = f"{HOOK_BEGIN}\nH\n{HOOK_END}\n"
    upsert_hook(path, block)
    text = path.read_text(encoding="utf-8")
    assert text.startswith("no-nl\n")
    assert "H" in text


def test_upsert_hook_end_at_eof_without_newline(tmp_path: Path) -> None:
    path = tmp_path / ".bashrc"
    path.write_text(f"x\n{HOOK_BEGIN}\nOLD\n{HOOK_END}", encoding="utf-8")
    upsert_hook(path, f"{HOOK_BEGIN}\nNEW\n{HOOK_END}\n")
    text = path.read_text(encoding="utf-8")
    assert "NEW" in text
    assert "OLD" not in text


def test_upsert_hook_end_before_begin(tmp_path: Path) -> None:
    path = tmp_path / ".bashrc"
    path.write_text(f"{HOOK_END}\nmid\n{HOOK_BEGIN}\nold\n", encoding="utf-8")
    upsert_hook(path, f"{HOOK_BEGIN}\nNEW\n{HOOK_END}\n")
    text = path.read_text(encoding="utf-8")
    assert text.startswith(f"{HOOK_END}\nmid\n")
    assert "NEW" in text
    assert "old" not in text


def test_write_activate_writes_posix_and_fish(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    write_activate(config, FakeRunner())
    assert config.activate_script.is_file()
    assert config.activate_fish.is_file()
    assert "IDF_PATH" in config.activate_script.read_text(encoding="utf-8")
    assert "activate.fish" in config.activate_fish.read_text(encoding="utf-8")


def test_install_shell_hooks_bash(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    host = FakeHost(tmp_path, shell_path="/bin/bash")
    (tmp_path / ".zshrc").write_text("# zsh\n", encoding="utf-8")
    hooked = install_shell_hooks(config, FakeRunner(), host)
    bashrc = tmp_path / ".bashrc"
    assert bashrc in hooked
    assert tmp_path / ".zshrc" in hooked
    text = bashrc.read_text(encoding="utf-8")
    assert HOOK_BEGIN in text
    assert str(config.activate_script) in text
    assert HOOK_BEGIN in (tmp_path / ".zshrc").read_text(encoding="utf-8")


def test_install_shell_hooks_fish_creates_config(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    host = FakeHost(tmp_path, shell_path="/usr/bin/fish")
    hooked = install_shell_hooks(config, FakeRunner(), host)
    fish_rc = tmp_path / ".config" / "fish" / "config.fish"
    assert fish_rc in hooked
    text = fish_rc.read_text(encoding="utf-8")
    assert "status is-interactive" in text
    assert str(config.activate_fish) in text


def test_install_shell_hooks_skip_and_dry_run(tmp_path: Path) -> None:
    skipped = install_shell_hooks(
        make_config(tmp_path, skip_shell=True),
        FakeRunner(),
        FakeHost(tmp_path),
    )
    assert skipped == []
    assert not (tmp_path / ".bashrc").exists()
    dry = install_shell_hooks(
        make_config(tmp_path / "dry", dry_run=True),
        FakeRunner(dry_run=True),
        FakeHost(tmp_path),
    )
    assert dry == []
    assert not (tmp_path / ".bashrc").exists()


def test_install_shell_hooks_unknown_shell_without_rc(tmp_path: Path) -> None:
    hooked = install_shell_hooks(
        make_config(tmp_path),
        FakeRunner(),
        FakeHost(tmp_path, shell_path="/usr/bin/nu"),
    )
    assert hooked == []


def test_install_shell_hooks_idempotent(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    host = FakeHost(tmp_path)
    install_shell_hooks(config, FakeRunner(), host)
    install_shell_hooks(config, FakeRunner(), host)
    text = (tmp_path / ".bashrc").read_text(encoding="utf-8")
    assert text.count(HOOK_BEGIN) == 1


def test_next_steps_mentions_auto_activate(tmp_path: Path) -> None:
    message = next_steps(make_config(tmp_path))
    assert "automatically" in message
    assert "source " in message
    skipped = next_steps(make_config(tmp_path, skip_shell=True))
    assert "automatically" not in skipped
    assert "source " in skipped


def test_run_setup_hooks_login_shell(tmp_path: Path) -> None:
    config = make_config(
        tmp_path,
        skip_packages=True,
        skip_esptool=True,
        skip_platformio=True,
        skip_idf=True,
        skip_rust=True,
        skip_udev=True,
        skip_dialout=True,
    )
    run_setup(config, FakeRunner(), FakeHost(tmp_path, shell_path="/bin/zsh"))
    assert config.activate_script.is_file()
    assert config.activate_fish.is_file()
    zshrc = tmp_path / ".zshrc"
    assert zshrc.is_file()
    assert HOOK_BEGIN in zshrc.read_text(encoding="utf-8")
