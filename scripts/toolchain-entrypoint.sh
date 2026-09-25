#!/bin/bash
# Activate the baked-in toolchain, then run the container command.
set -euo pipefail

prefix="/opt/esp32-dev"
export ESP32_DEV_PREFIX="$prefix"
# shellcheck disable=SC1091
. "${prefix}/activate.sh"

# espup's xtensa-esp-elf gcc is older than the one ESP-IDF install.sh downloaded.
# activate.sh puts the espup copy first, and idf.py then refuses to configure.
tools="${IDF_TOOLS_PATH:-$prefix/.espressif}"
idf_gcc="$(find "$tools" -type f -name xtensa-esp32-elf-gcc -path '*/xtensa-esp-elf/bin/*' 2>/dev/null | head -n 1 || true)"
if [ -n "$idf_gcc" ]; then
  PATH="$(dirname "$idf_gcc"):$PATH"
  export PATH
fi

if [ "$#" -eq 0 ]; then
  set -- bash
fi
exec "$@"
