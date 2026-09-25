"""The firmware toolchain image is defined and wired into CI."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_toolchain_stage_runs_setup() -> None:
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    start = text.index("FROM runtime AS toolchain")
    stage = text[start:]
    assert "--prefix /opt/esp32-dev" in stage
    assert "--skip-udev" in stage
    assert "--skip-dialout" in stage
    assert "--skip-shell" in stage
    assert "--no-sudo" in stage
    assert "IDF_TOOLS_PATH=/opt/esp32-dev/.espressif" in stage
    assert "PLATFORMIO_CORE_DIR=/opt/esp32-dev/platformio" in stage
    assert 'ENTRYPOINT ["/app/scripts/toolchain-entrypoint.sh"]' in stage


def test_toolchain_entrypoint_is_valid_bash() -> None:
    script = ROOT / "scripts" / "toolchain-entrypoint.sh"
    subprocess.run(["bash", "-n", str(script)], check=True)
    text = script.read_text(encoding="utf-8")
    assert "activate.sh" in text
    assert 'exec "$@"' in text


def test_container_workflow_publishes_toolchain_image() -> None:
    text = (ROOT / ".github" / "workflows" / "container.yml").read_text(encoding="utf-8")
    assert "target: toolchain" in text
    assert "-toolchain" in text
    assert "push: ${{ github.event_name != 'pull_request' }}" in text
    assert "linux/amd64" in text
    assert "linux/arm64" in text


def test_compose_firmware_service_uses_toolchain_stage() -> None:
    text = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert "target: toolchain" in text
    assert "/workspace" in text
