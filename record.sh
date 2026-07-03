#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [[ ! -x build/unitree_rerun_recorder ]]; then
  mkdir -p build
  cmake -S . -B build
  cmake --build build -j8
fi

exec build/unitree_rerun_recorder "$@"
