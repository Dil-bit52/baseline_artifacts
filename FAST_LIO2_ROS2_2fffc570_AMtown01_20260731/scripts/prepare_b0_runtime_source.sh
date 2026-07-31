#!/usr/bin/env bash
set -euo pipefail

BASE=/data/fastlio_baseline
SOURCE="$BASE/source/b0_vanilla"
RUNTIME="$BASE/workspaces/b0/src/fast_lio"

if [[ -L "$RUNTIME" ]]; then
  test "$(readlink "$RUNTIME")" = "$SOURCE"
  unlink "$RUNTIME"
fi
if [[ ! -e "$RUNTIME" ]]; then
  git clone --no-hardlinks "$SOURCE" "$RUNTIME"
  git -C "$RUNTIME" checkout --detach 2fffc570a25d0df172720bac034fbdb6a13d2162
  git -C "$RUNTIME" config submodule.include/ikd-Tree.url "$SOURCE/include/ikd-Tree"
  git -C "$RUNTIME" -c protocol.file.allow=always submodule update --init --recursive
fi
test -z "$(git -C "$SOURCE" status --porcelain=v2)"
test -z "$(git -C "$RUNTIME" status --porcelain=v2)"

printf '%s\n' \
  "fast_lio -> independent runtime clone of $SOURCE (binary was built before replacement from identical Commit)" \
  "livox_ros_driver2 -> independent clone with official ROS2 generated files" \
  >"$BASE/workspaces/b0/source_layout.txt"
echo "Prepared independent B0 runtime source copy"
