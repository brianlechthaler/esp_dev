#!/bin/bash
# Activate the baked-in toolchain, then run the container command.
set -euo pipefail

prefix="${ESP32_DEV_PREFIX:-/opt/esp32-dev}"
# shellcheck disable=SC1091
. "${prefix}/activate.sh"

if [ "$#" -eq 0 ]; then
  set -- bash
fi
exec "$@"
