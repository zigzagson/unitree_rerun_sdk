#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [[ ! -x build/unitree_rerun_recorder ]]; then
  mkdir -p build
  cmake -S . -B build
  cmake --build build -j8
fi

if [[ $# -gt 0 && "${1:0:1}" != "-" ]]; then
  interface="$1"
  shift
  tmp_conf="$(mktemp /tmp/unitree_rerun_recorder.XXXXXX.conf)"
  trap 'rm -f "$tmp_conf"' EXIT
  sed "s/^network_interface=.*/network_interface=${interface}/" build/recorder.conf > "$tmp_conf"
  build/unitree_rerun_recorder --config "$tmp_conf" "$@"
  exit $?
fi

exec build/unitree_rerun_recorder "$@"
