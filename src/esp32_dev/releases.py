"""Look up current tool releases."""

from __future__ import annotations

import json
import logging
from urllib.error import URLError
from urllib.request import Request, urlopen

from esp32_dev.errors import SetupError

logger = logging.getLogger("esp32_dev")

GITHUB_IDF_LATEST_RELEASE_URL = "https://api.github.com/repos/espressif/esp-idf/releases/latest"
LATEST_ALIASES = frozenset({"latest", "stable"})
_USER_AGENT = "esp32-dev"


def is_latest_alias(version: str) -> bool:
    """Return whether ``version`` means “use the current GitHub release”."""
    return version.strip().lower() in LATEST_ALIASES


def fetch_latest_idf_release_tag(
    url: str = GITHUB_IDF_LATEST_RELEASE_URL,
) -> str:
    """Return the latest non-prerelease ESP-IDF git tag from GitHub."""
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": _USER_AGENT,
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = response.read().decode("utf-8")
    except (OSError, URLError) as exc:
        raise SetupError(f"unable to look up the latest ESP-IDF release: {exc}") from exc
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise SetupError("latest ESP-IDF release response was not valid JSON") from exc
    if not isinstance(data, dict):
        raise SetupError("latest ESP-IDF release response was not an object")
    tag = data.get("tag_name")
    if not isinstance(tag, str) or not tag.strip():
        raise SetupError("latest ESP-IDF release did not include a tag name")
    return tag.strip()


def resolve_idf_version(version: str) -> str:
    """Return a concrete ESP-IDF git ref, resolving ``latest``/``stable`` via GitHub."""
    if not is_latest_alias(version):
        return version
    tag = fetch_latest_idf_release_tag()
    logger.info("latest ESP-IDF release is %s", tag)
    return tag
