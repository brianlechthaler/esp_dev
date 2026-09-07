#!/usr/bin/env python3
"""Install the ESP32 dest toolkit agent skill into AI coding tools."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_SRC = _ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from esp32_dev.skill_install import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(repo_root=_ROOT))
