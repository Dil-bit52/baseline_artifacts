#!/usr/bin/env bash
set -euo pipefail

WS=/data/fastlio_baseline/workspaces/b0
OUT="$WS/build_acceptance"
BIN="$WS/install/fast_lio/lib/fast_lio/fastlio_mapping"
mkdir -p "$OUT"

test "$(cat "$WS/build_exit_code.txt")" = "0"
test -x "$BIN"
test -z "$(git -C /data/fastlio_baseline/source/b0_vanilla status --porcelain=v2)"

set +u
source /opt/ros/humble/setup.bash
source "$WS/install/setup.bash"
set -u

ros2 pkg executables fast_lio >"$OUT/ros2_pkg_executables.txt"
ros2 launch fast_lio mapping.launch.py --show-args >"$OUT/launch_args.txt"
find "$WS/install" -type f -name fastlio_mapping >"$OUT/binary_paths.txt"
ldd "$BIN" >"$OUT/ldd.txt"
if grep -q 'not found' "$OUT/ldd.txt"; then
  echo "Unresolved dynamic libraries" >&2
  exit 1
fi
sha256sum "$BIN" >"$OUT/fastlio_mapping.sha256"
sha256sum /usr/local/lib/liblivox_lidar_sdk_shared.so >"$OUT/livox_sdk_shared.sha256"

{
  echo "build_exit_code=0"
  echo "binary=$BIN"
  echo "binary_sha256=$(cut -d' ' -f1 "$OUT/fastlio_mapping.sha256")"
  echo "ldd_not_found_count=0"
  echo "fast_lio_commit=$(git -C /data/fastlio_baseline/source/b0_vanilla rev-parse HEAD)"
  echo "ikd_tree_commit=$(git -C /data/fastlio_baseline/source/b0_vanilla/include/ikd-Tree rev-parse HEAD)"
  echo "source_clean=true"
} >"$OUT/summary.txt"

echo "B0 build acceptance passed"
