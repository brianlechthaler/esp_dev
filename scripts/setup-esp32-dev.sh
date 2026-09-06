#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"

if [[ $# -eq 0 ]]; then
  exec python3 -m esp32_dev setup
fi
exec python3 -m esp32_dev "$@"
