#!/usr/bin/env bash
set -euo pipefail

BASE=/data/fastlio_baseline
OUT="$BASE/datasets/inspection/tail_1342s"
BAG="$BASE/datasets/AMtown01_driver2"
export ROS_DOMAIN_ID=48
mkdir -p "$OUT"
set +u
source /opt/ros/humble/setup.bash
source "$BASE/workspaces/b0/install/setup.bash"
set -u

python3 /workspace/baseline_artifacts/scripts/inspect_livox_validity.py \
  --output "$OUT/tail_validity.csv" --duration 18 >"$OUT/inspector.log" 2>&1 &
inspector_pid=$!
cleanup() {
  if kill -0 "$inspector_pid" 2>/dev/null; then kill -TERM "$inspector_pid" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM
sleep 1
ros2 bag play "$BAG" --clock --rate 1.0 --start-offset 1342 \
  --topics /livox/lidar /livox/imu >"$OUT/bag_play.log" 2>&1
bag_rc=$?
wait "$inspector_pid"
inspector_rc=$?
printf 'bag_play=%s\ninspector=%s\n' "$bag_rc" "$inspector_rc" >"$OUT/exit_codes.txt"
trap - EXIT INT TERM
test "$bag_rc" = "0"
test "$inspector_rc" = "0"
echo "Dataset tail validity inspection complete"
