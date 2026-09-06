"""Tests for ``python -m esp32_dev``."""

from __future__ import annotations

import runpy
import sys

import pytest

from esp32_dev.cli import console_entry


@pytest.mark.filterwarnings("ignore:.*found in sys.modules.*:RuntimeWarning")
def test_main_module_import_and_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    import esp32_dev.__main__ as main_mod

    assert main_mod.console_entry is console_entry
    sys.modules.pop("esp32_dev.__main__", None)
    monkeypatch.setattr(sys, "argv", ["esp32_dev"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("esp32_dev", run_name="__main__")
    assert exc.value.code == 0
