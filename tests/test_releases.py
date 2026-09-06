"""Tests for GitHub release lookup."""

from __future__ import annotations

import json
from urllib.error import URLError

import pytest

from esp32_dev.errors import SetupError
from esp32_dev.releases import (
    GITHUB_IDF_LATEST_RELEASE_URL,
    fetch_latest_idf_release_tag,
    is_latest_alias,
    resolve_idf_version,
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


def test_is_latest_alias() -> None:
    assert is_latest_alias("latest") is True
    assert is_latest_alias("LATEST") is True
    assert is_latest_alias(" stable ") is True
    assert is_latest_alias("v6.1") is False
    assert is_latest_alias("master") is False


def test_resolve_explicit_version_skips_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_url: str = "") -> str:
        raise AssertionError("should not fetch")

    monkeypatch.setattr("esp32_dev.releases.fetch_latest_idf_release_tag", boom)
    assert resolve_idf_version("v6.1") == "v6.1"


def test_resolve_latest_uses_github_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("esp32_dev.releases.fetch_latest_idf_release_tag", lambda: "v6.1")
    assert resolve_idf_version("latest") == "v6.1"
    assert resolve_idf_version("STABLE") == "v6.1"


def test_fetch_latest_success(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_open(request: object, timeout: float = 0) -> FakeResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse(json.dumps({"tag_name": " v6.1 "}))

    monkeypatch.setattr("esp32_dev.releases.urlopen", fake_open)
    assert fetch_latest_idf_release_tag() == "v6.1"
    request = captured["request"]
    assert getattr(request, "full_url", "") == GITHUB_IDF_LATEST_RELEASE_URL
    assert captured["timeout"] == 30
    headers = getattr(request, "headers", {})
    header_text = " ".join(f"{key}:{value}" for key, value in dict(headers).items())
    assert "esp32-dev" in header_text


def test_fetch_latest_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_open(_request: object, timeout: float = 0) -> FakeResponse:
        raise URLError("offline")

    monkeypatch.setattr("esp32_dev.releases.urlopen", fake_open)
    with pytest.raises(SetupError, match="unable to look up the latest ESP-IDF release"):
        fetch_latest_idf_release_tag()


def test_fetch_latest_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("esp32_dev.releases.urlopen", lambda *_a, **_k: FakeResponse("{not-json"))
    with pytest.raises(SetupError, match="not valid JSON"):
        fetch_latest_idf_release_tag()


def test_fetch_latest_non_object(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "esp32_dev.releases.urlopen",
        lambda *_a, **_k: FakeResponse(json.dumps(["v6.1"])),
    )
    with pytest.raises(SetupError, match="not an object"):
        fetch_latest_idf_release_tag()


def test_fetch_latest_missing_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "esp32_dev.releases.urlopen",
        lambda *_a, **_k: FakeResponse(json.dumps({"name": "ESP-IDF"})),
    )
    with pytest.raises(SetupError, match="did not include a tag name"):
        fetch_latest_idf_release_tag()


def test_fetch_latest_blank_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "esp32_dev.releases.urlopen",
        lambda *_a, **_k: FakeResponse(json.dumps({"tag_name": "  "})),
    )
    with pytest.raises(SetupError, match="did not include a tag name"):
        fetch_latest_idf_release_tag()


def test_fetch_latest_non_string_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "esp32_dev.releases.urlopen",
        lambda *_a, **_k: FakeResponse(json.dumps({"tag_name": 61})),
    )
    with pytest.raises(SetupError, match="did not include a tag name"):
        fetch_latest_idf_release_tag()
