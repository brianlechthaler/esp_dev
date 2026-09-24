"""Pinned installer toolchain versions.

``scripts/toolchain-versions.py apply`` rewrites the assignment lines below.
Do not duplicate these numbers in docs.
"""

IDF_VERSION = "v6.1"
ESPTOOL_VERSION = "5.4.0"
PLATFORMIO_VERSION = "6.2.0"
RUST_VERSION = "1.98.1"
ESPUP_VERSION = "0.17.1"
LDPROXY_VERSION = "0.3.5"
ESPFLASH_VERSION = "4.6.0"
CARGO_ESPFLASH_VERSION = "4.6.0"
ESP_GENERATE_VERSION = "1.4.0"

CARGO_CRATE_VERSIONS: dict[str, str] = {
    "espup": ESPUP_VERSION,
    "ldproxy": LDPROXY_VERSION,
    "espflash": ESPFLASH_VERSION,
    "cargo-espflash": CARGO_ESPFLASH_VERSION,
    "esp-generate": ESP_GENERATE_VERSION,
}
