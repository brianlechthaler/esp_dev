#!/usr/bin/env python3
"""Print or update the toolchain versions pinned in this repo."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from esp32_dev.toolchain import main

if __name__ == "__main__":
    raise SystemExit(main())
