#!/usr/bin/env bash
# Run a command inside the shared ESP32 dest environment (pio, idf.py, esptool, cargo).
set -euo pipefail

prefix="${ESP32_DEV_PREFIX:-${HOME}/.esp32-dev}"
activate="${prefix}/activate.sh"
if [ ! -f "$activate" ]; then
  echo "error: ESP32 dest environment not found at ${prefix}" >&2
  echo "Install it from the esp_dev repo: ./scripts/setup-esp32-dev.sh" >&2
  exit 1
fi
# shellcheck disable=SC1090
. "$activate"
if [ "$#" -eq 0 ]; then
  echo "ESP32_DEV_PREFIX=${prefix}"
  command -v pio >/dev/null && pio --version || true
  command -v idf.py >/dev/null && echo "idf.py: $(command -v idf.py)" || true
  python -m esptool version >/dev/null 2>&1 && python -m esptool version || true
  command -v rustc >/dev/null && rustc --version || true
  command -v cargo >/dev/null && cargo --version || true
  exit 0
fi
exec "$@"
