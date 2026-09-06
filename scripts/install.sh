#!/usr/bin/env bash
# Install the ESP32 development environment and auto-activate it in common shells.
#
#   ./scripts/install.sh [setup-args...]     # install and hook future shells
#   . ./scripts/install.sh [setup-args...]   # also activate this bash/zsh shell

_esp32_dev_sourced=0
if [ -n "${ZSH_VERSION:-}" ]; then
  case ${ZSH_EVAL_CONTEXT:-} in *:file:*) _esp32_dev_sourced=1 ;; esac
elif [ -n "${BASH_VERSION:-}" ] && [ "${BASH_SOURCE[0]:-}" != "$0" ]; then
  _esp32_dev_sourced=1
fi

if [ "$_esp32_dev_sourced" -eq 0 ]; then
  set -euo pipefail
fi

_esp32_dev_prefix="${HOME}/.esp32-dev"

_esp32_dev_install() {
  local root script prev arg status=0
  if [ -n "${BASH_SOURCE[0]:-}" ]; then
    script="${BASH_SOURCE[0]}"
  else
    script="$0"
  fi
  root="$(cd "$(dirname "$script")/.." && pwd)"
  prev=""
  for arg in "$@"; do
    case "$arg" in
      --prefix=*) _esp32_dev_prefix="${arg#--prefix=}" ;;
    esac
    if [ "$prev" = "--prefix" ]; then
      _esp32_dev_prefix="$arg"
    fi
    prev="$arg"
  done
  PYTHONPATH="${root}/src${PYTHONPATH:+:$PYTHONPATH}" python3 -m esp32_dev setup "$@" || status=$?
  return "$status"
}

_esp32_dev_status=0
_esp32_dev_install "$@" || _esp32_dev_status=$?
unset -f _esp32_dev_install
if [ "$_esp32_dev_status" -eq 0 ] && [ "$_esp32_dev_sourced" -eq 1 ] && [ -f "${_esp32_dev_prefix}/activate.sh" ]; then
  # shellcheck disable=SC1090
  . "${_esp32_dev_prefix}/activate.sh"
fi
unset _esp32_dev_prefix
if [ "$_esp32_dev_sourced" -eq 1 ]; then
  unset _esp32_dev_sourced
  return "$_esp32_dev_status"
fi
exit "$_esp32_dev_status"
