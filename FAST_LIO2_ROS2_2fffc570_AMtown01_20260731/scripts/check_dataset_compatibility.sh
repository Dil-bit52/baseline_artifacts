#!/usr/bin/env bash
set -euo pipefail

BASE=/data/fastlio_baseline
WS="$BASE/workspaces/b0"
OUT="$BASE/datasets/inspection/runtime_compatibility"
BAG="$BASE/datasets/AMtown01_driver2"
export ROS_DOMAIN_ID=47
mkdir -p "$OUT"

set +u
source /opt/ros/humble/setup.bash
source "$WS/install/setup.bash"
set -u

ros2 node list --no-daemon --spin-time 2 >"$OUT/nodes_before.txt"
if [[ -s "$OUT/nodes_before.txt" ]]; then
  echo "ROS domain 47 is not empty" >&2
  exit 4
fi

python3 /workspace/baseline_artifacts/scripts/check_pointcloud.py \
  --samples 5 --timeout 25 >"$OUT/message_samples.json" 2>"$OUT/inspector.log" &
inspector_pid=$!

set +e
timeout --signal=INT --kill-after=5s 20s \
  ros2 bag play "$BAG" --clock --start-offset 0 \
  --topics /livox/lidar /livox/imu >"$OUT/bag_play.log" 2>&1 &
bag_pid=$!
set -e
cleanup() {
  if kill -0 "$bag_pid" 2>/dev/null; then
    kill -INT "$bag_pid" 2>/dev/null || true
  fi
  if kill -0 "$inspector_pid" 2>/dev/null; then
    kill -TERM "$inspector_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

set +e
wait "$bag_pid"
bag_rc=$?
wait "$inspector_pid"
inspector_rc=$?
set -e
printf 'bag_play=%s\ninspector=%s\n' "$bag_rc" "$inspector_rc" >"$OUT/exit_codes.txt"
timeout 5s ros2 topic list -t --no-daemon --spin-time 2 >"$OUT/topics_after_play.txt" || true
trap - EXIT INT TERM

test "$inspector_rc" = "0"
test "$bag_rc" = "124" -o "$bag_rc" = "0"
echo "Dataset runtime compatibility check passed"
