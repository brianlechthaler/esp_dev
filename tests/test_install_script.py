"""Tests for the repo-root ``install.py`` wrapper."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest


def test_install_script_entrypoint(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(sys, "argv", [str(root / "install.py"), "--list-agents"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(root / "install.py"), run_name="__main__")
    assert exc.value.code == 0
    assert "cursor" in capsys.readouterr().out
