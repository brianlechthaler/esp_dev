#!/usr/bin/env bash
# Run a firmware command in the toolchain image on a remote host.
# The image entrypoint sources /opt/esp32-dev/activate.sh, then execs the
# command. Pass cargo, idf.py, or pio directly; a login shell resets PATH.
set -euo pipefail

image="ghcr.io/brianlechthaler/esp_dev-toolchain:main"
host=""
remote=""
remote_set=0
workdir="."
envs=()
cmd=()

die() {
  printf '%s\n' "$1" >&2
  exit 2
}

usage() {
  cat <<EOF
Usage: scripts/remote-build.sh --host HOST --remote DIR [options] -- COMMAND...

Run COMMAND in ${image} on a remote host over SSH.
The image entrypoint sources /opt/esp32-dev/activate.sh and execs COMMAND.
Pass cargo, idf.py, or pio directly. Do not wrap COMMAND in a login shell.

  --host HOST       SSH destination (required)
  --remote DIR      Remote tree mounted at /workspace (required).
                    Relative paths and ~/... are under the remote \$HOME.
                    Example: builds/espcap
  --workdir REL     Directory under /workspace (default: .)
  --env KEY=VALUE   Repeatable docker -e variable
  --image IMAGE     Default: ${image}
  -h, --help        Show this help

ghcr.io/brianlechthaler/esp_dev is the installer CLI, not the build image.
EOF
}

require_value() {
  local flag=$1
  if [[ $# -lt 2 || -z ${2:-} || ${2:0:2} == -- ]]; then
    die "${flag} requires a value"
  fi
}

while [[ $# -gt 0 ]]; do
  case $1 in
    -h | --help)
      usage
      exit 0
      ;;
    --host)
      require_value "$@"
      host=$2
      shift 2
      ;;
    --remote)
      require_value "$@"
      remote=$2
      remote_set=1
      shift 2
      ;;
    --workdir)
      require_value "$@"
      workdir=$2
      shift 2
      ;;
    --image)
      require_value "$@"
      image=$2
      shift 2
      ;;
    --env)
      require_value "$@"
      [[ $2 == *=* ]] || die "--env must be KEY=VALUE"
      envs+=("$2")
      shift 2
      ;;
    --)
      shift
      cmd=("$@")
      break
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

[[ -n $host ]] || die "--host requires a value"
[[ $remote_set -eq 1 ]] || die "--remote requires a value"
[[ ${#cmd[@]} -gt 0 ]] || die "missing command"

absolute=0
rel=""
# Keep the tilde and $HOME literal so they expand on the remote host.
# shellcheck disable=SC2088,SC2016
case $remote in
  "~/"*) rel=${remote#"~/"} ;;
  '$HOME'/*) rel=${remote#'$HOME'/} ;;
  /*) absolute=1 ;;
  *) rel=$remote ;;
esac

if [[ $absolute -eq 1 ]]; then
  remote=${remote%/}
  [[ -n $remote && $remote != / ]] || die "remote directory must not be empty"
else
  rel=${rel%/}
  if [[ -z $rel || $rel == *..* || $rel == /* || ! $rel =~ ^[A-Za-z0-9._/-]+$ ]]; then
    die "remote directory must be a relative path under the remote home"
  fi
fi

workdir=${workdir%/}
if [[ -z $workdir || $workdir == . ]]; then
  container_wd=/workspace
else
  container_wd=/workspace/${workdir#/}
fi

quote() {
  printf '%q' "$1"
}

words=()
words+=("$(quote docker)" "$(quote run)" "$(quote --rm)" "$(quote -v)")
if [[ $absolute -eq 1 ]]; then
  words+=("$(quote "${remote}:/workspace")")
else
  words+=("\"\$HOME/${rel}:/workspace\"")
fi
words+=("$(quote -w)" "$(quote "$container_wd")")
if [[ ${#envs[@]} -gt 0 ]]; then
  for pair in "${envs[@]}"; do
    words+=("$(quote -e)" "$(quote "$pair")")
  done
fi
words+=("$(quote "$image")")
for arg in "${cmd[@]}"; do
  words+=("$(quote "$arg")")
done

remote_cmd=""
for word in "${words[@]}"; do
  remote_cmd+="${remote_cmd:+ }${word}"
done

exec ssh -o BatchMode=yes -- "$host" "$remote_cmd"
