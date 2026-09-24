"""Tests for pinned toolchain lookup and rewrite."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.error import URLError

import pytest

from esp32_dev.errors import SetupError
from esp32_dev.toolchain import (
    PIN_NAMES,
    apply_updates,
    current_pins,
    fetch_crate_version,
    fetch_pypi_version,
    fetch_rust_stable_version,
    format_pins,
    latest_pins,
    main,
    parse_rust_stable_version,
    pins_path,
    read_pin_file,
    render_pins,
)


class FakeResponse:
    def __init__(self, body: str) -> None:
        self._body = body.encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


RUST_MANIFEST = """\
[pkg.cargo]
version = "0.99.0 (hash date)"

[pkg.rust]
version = "1.98.1 (hash 2026-09-01)"

[pkg.rust.target.x86_64-unknown-linux-gnu]
available = true
"""


def test_current_pins_match_file() -> None:
    assert set(current_pins()) == set(PIN_NAMES)
    assert read_pin_file(pins_path()) == current_pins()
    assert format_pins(current_pins()).splitlines()[0].startswith("IDF_VERSION=")


def test_parse_rust_stable_version() -> None:
    assert parse_rust_stable_version(RUST_MANIFEST) == "1.98.1"


def test_parse_rust_stable_missing_section() -> None:
    with pytest.raises(SetupError, match="did not include a rustc version"):
        parse_rust_stable_version('[pkg.cargo]\nversion = "1.0.0"\n')


def test_parse_rust_stable_section_ends() -> None:
    text = '[pkg.rust]\n[pkg.other]\nversion = "1.2.3"\n'
    with pytest.raises(SetupError, match="did not include a rustc version"):
        parse_rust_stable_version(text)


def test_parse_rust_stable_bad_version_line() -> None:
    text = '[pkg.rust]\nversion = "not-semver"\n'
    with pytest.raises(SetupError, match="did not include a rustc version"):
        parse_rust_stable_version(text)


def test_request_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_open(request: object, timeout: float = 0) -> FakeResponse:
        assert timeout == 30
        assert getattr(request, "full_url", "") == "https://example.test/pins"
        return FakeResponse("ok")

    monkeypatch.setattr("esp32_dev.toolchain.urlopen", fake_open)
    from esp32_dev.toolchain import _request

    assert _request("https://example.test/pins") == "ok"


def test_fetch_pypi_and_crate(monkeypatch: pytest.MonkeyPatch) -> None:
    payloads = {
        "esptool": {"info": {"version": " 9.9.9 "}},
        "espup": {"crate": {"newest_version": " 1.2.3 "}},
    }

    def fake_request(url: str) -> str:
        if "esptool" in url:
            return json.dumps(payloads["esptool"])
        return json.dumps(payloads["espup"])

    monkeypatch.setattr("esp32_dev.toolchain._request", fake_request)
    assert fetch_pypi_version("esptool") == "9.9.9"
    assert fetch_crate_version("espup") == "1.2.3"


def test_fetch_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_open(_request: object, timeout: float = 0) -> FakeResponse:
        raise URLError("offline")

    monkeypatch.setattr("esp32_dev.toolchain.urlopen", fake_open)
    with pytest.raises(SetupError, match="unable to look up toolchain versions"):
        fetch_pypi_version("esptool")


def test_fetch_invalid_payloads(monkeypatch: pytest.MonkeyPatch) -> None:
    bodies = iter(
        [
            "{",
            json.dumps(["nope"]),
            json.dumps({}),
            json.dumps({"info": []}),
            json.dumps({"info": {"version": "  "}}),
            json.dumps({"info": {"version": 1}}),
            json.dumps({}),
            json.dumps({"crate": []}),
            json.dumps({"crate": {"newest_version": ""}}),
            json.dumps({"crate": {"newest_version": 1}}),
        ]
    )
    monkeypatch.setattr("esp32_dev.toolchain._request", lambda _url: next(bodies))
    with pytest.raises(SetupError, match="not valid JSON"):
        fetch_pypi_version("esptool")
    with pytest.raises(SetupError, match="not an object"):
        fetch_pypi_version("esptool")
    with pytest.raises(SetupError, match="package info"):
        fetch_pypi_version("esptool")
    with pytest.raises(SetupError, match="package info"):
        fetch_pypi_version("esptool")
    with pytest.raises(SetupError, match="did not include a version"):
        fetch_pypi_version("esptool")
    with pytest.raises(SetupError, match="did not include a version"):
        fetch_pypi_version("esptool")
    with pytest.raises(SetupError, match="crate metadata"):
        fetch_crate_version("espup")
    with pytest.raises(SetupError, match="crate metadata"):
        fetch_crate_version("espup")
    with pytest.raises(SetupError, match="did not include a version"):
        fetch_crate_version("espup")
    with pytest.raises(SetupError, match="did not include a version"):
        fetch_crate_version("espup")


def test_fetch_rust_stable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("esp32_dev.toolchain._request", lambda _url: RUST_MANIFEST)
    assert fetch_rust_stable_version() == "1.98.1"


def test_latest_pins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("esp32_dev.toolchain.fetch_latest_idf_release_tag", lambda: "v9.9")
    monkeypatch.setattr("esp32_dev.toolchain.fetch_pypi_version", lambda name: f"pypi-{name}")
    monkeypatch.setattr("esp32_dev.toolchain.fetch_crate_version", lambda name: f"crate-{name}")
    monkeypatch.setattr("esp32_dev.toolchain.fetch_rust_stable_version", lambda: "1.2.3")
    latest = latest_pins()
    assert latest["IDF_VERSION"] == "v9.9"
    assert latest["ESPTOOL_VERSION"] == "pypi-esptool"
    assert latest["ESPUP_VERSION"] == "crate-espup"
    assert latest["RUST_VERSION"] == "1.2.3"


def test_read_and_render_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "pins.py"
    values = current_pins()
    path.write_text(render_pins(values), encoding="utf-8")
    assert read_pin_file(path) == values


def test_read_pin_file_missing(tmp_path: Path) -> None:
    path = tmp_path / "pins.py"
    path.write_text('IDF_VERSION = "v1"\n', encoding="utf-8")
    with pytest.raises(SetupError, match="missing"):
        read_pin_file(path)


def test_render_pins_missing() -> None:
    with pytest.raises(SetupError, match="cannot render pins"):
        render_pins({"IDF_VERSION": "v1"})


def test_apply_updates_noop_and_rewrite(tmp_path: Path) -> None:
    path = tmp_path / "pins.py"
    values = current_pins()
    path.write_text(render_pins(values), encoding="utf-8")
    assert apply_updates(path, dict(values)) == []
    newer = dict(values)
    newer["ESPTOOL_VERSION"] = "9.9.9"
    changes = apply_updates(path, newer)
    assert changes == [("ESPTOOL_VERSION", values["ESPTOOL_VERSION"], "9.9.9")]
    assert read_pin_file(path)["ESPTOOL_VERSION"] == "9.9.9"


def test_main_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([]) == 2
    assert "usage:" in capsys.readouterr().err
    assert main(["current", "extra"]) == 2
    assert main(["current"]) == 0
    assert "IDF_VERSION=" in capsys.readouterr().out
    monkeypatch.setattr("esp32_dev.toolchain.latest_pins", current_pins)
    assert main(["latest"]) == 0
    capsys.readouterr()
    assert main(["apply"]) == 0
    assert capsys.readouterr().out.strip() == "already current"
    path = tmp_path / "pins.py"
    path.write_text(render_pins(current_pins()), encoding="utf-8")
    monkeypatch.setattr("esp32_dev.toolchain.pins_path", lambda: path)
    bumped = dict(current_pins())
    bumped["RUST_VERSION"] = "9.9.9"
    monkeypatch.setattr("esp32_dev.toolchain.latest_pins", lambda: bumped)
    assert main(["apply"]) == 0
    assert "updated RUST_VERSION" in capsys.readouterr().out


def test_main_defaults_to_argv(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("esp32_dev.toolchain.sys.argv", ["toolchain-versions.py", "current"])
    assert main() == 0
    assert "ESPTOOL_VERSION=" in capsys.readouterr().out
