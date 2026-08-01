#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 <run_id> <full|wall_seconds> <enabled|disabled> [play_rate] [ros_domain_id]" >&2
}

[[ $# -ge 3 && $# -le 5 ]] || { usage; exit 2; }
RUN_ID=$1
PLAY_LIMIT=$2
MODE=$3
PLAY_RATE=${4:-1.0}
ROS_DOMAIN=${5:-57}
[[ "$MODE" == "enabled" || "$MODE" == "disabled" ]] || { usage; exit 2; }

STAGE=/workspace/stage2_artifacts
WS=/workspace/stage2_workspaces/b2
RUN="$STAGE/raw/runs/$RUN_ID"
BAG=/data/fastlio_baseline/datasets/AMtown01_driver2
BIN="$WS/install/fast_lio/lib/fast_lio/fastlio_mapping"
SOURCE="$WS/src/fast_lio"
DATASET_SHA256=6f3c85f54982d88d1dd2707815922e5a77fa7d64a787a608ac43d6a70f819586

test -x "$BIN"
test -d "$BAG"
test ! -e "$RUN"
mkdir -p "$RUN"

if [[ "$MODE" == "enabled" ]]; then
  cp "$STAGE/config/b2_lifecycle.yaml" "$RUN/config.yaml"
  python3 - "$RUN/config.yaml" "$RUN/lifecycle" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
output = sys.argv[2]
text = path.read_text(encoding="utf-8")
if text.count("__OUTPUT_DIRECTORY__") != 1:
    raise SystemExit("expected exactly one lifecycle output token")
path.write_text(text.replace("__OUTPUT_DIRECTORY__", output), encoding="utf-8")
PY
else
  cp "$STAGE/config/b2_disabled.yaml" "$RUN/config.yaml"
fi

sha256sum "$RUN/config.yaml" >"$RUN/config.sha256"
git -C "$SOURCE" status --porcelain=v2 --branch --ignore-submodules=all >"$RUN/git_status.txt"
git -C "$SOURCE" rev-parse HEAD >"$RUN/git_head.txt"
sha256sum "$BIN" >"$RUN/binary.sha256"

export ROS_DOMAIN_ID="$ROS_DOMAIN"
export FASTLIO_METRICS_CSV="$RUN/frame_metrics.csv"

set +u
source /opt/ros/humble/setup.bash
source "$WS/install/setup.bash"
set -u

nodes_before=$(ros2 node list --no-daemon --spin-time 2 || true)
if [[ -n "$nodes_before" ]]; then
  printf '%s\n' "$nodes_before" >"$RUN/nodes_before.txt"
  echo "ROS domain $ROS_DOMAIN is not empty" >&2
  exit 4
fi

{
  echo "variant=B2 Passive Voxel Lifecycle Observer"
  echo "run_id=$RUN_ID"
  echo "mode=$MODE"
  echo "ROS_DOMAIN_ID=$ROS_DOMAIN_ID"
  echo "launch=ros2 launch fast_lio mapping.launch.py config_path:=$RUN config_file:=config.yaml use_sim_time:=true rviz:=false"
  echo "play=ros2 bag play $BAG --clock --rate $PLAY_RATE --delay 5 --topics /livox/lidar /livox/imu"
  echo "record=ros2 bag record --storage mcap -o $RUN/estimated_odometry /Odometry /tf /tf_static"
} >"$RUN/commands.txt"

setsid ros2 launch fast_lio mapping.launch.py \
  config_path:="$RUN" config_file:=config.yaml use_sim_time:=true rviz:=false \
  >"$RUN/fastlio.log" 2>&1 &
launch_pid=$!
recorder_pid=""
latency_pid=""
process_monitor_pid=""

cleanup() {
  set +e
  for entry in "$recorder_pid" "$latency_pid"; do
    if [[ -n "$entry" ]] && kill -0 "$entry" 2>/dev/null; then
      kill -INT -- "-$entry" 2>/dev/null || kill -INT "$entry" 2>/dev/null || true
    fi
  done
  if [[ -n "$launch_pid" ]] && kill -0 "$launch_pid" 2>/dev/null; then
    kill -INT -- "-$launch_pid" 2>/dev/null || kill -INT "$launch_pid" 2>/dev/null || true
  fi
  shutdown_deadline=$((SECONDS + 600))
  while [[ -n "$launch_pid" ]] && kill -0 "$launch_pid" 2>/dev/null \
      && (( SECONDS < shutdown_deadline )); do
    sleep 1
  done
  if [[ -n "$process_monitor_pid" ]] && kill -0 "$process_monitor_pid" 2>/dev/null; then
    kill -INT -- "-$process_monitor_pid" 2>/dev/null \
      || kill -INT "$process_monitor_pid" 2>/dev/null || true
  fi
  sleep 1
  for entry in "$recorder_pid" "$latency_pid" "$process_monitor_pid" "$launch_pid"; do
    if [[ -n "$entry" ]] && kill -0 "$entry" 2>/dev/null; then
      kill -TERM -- "-$entry" 2>/dev/null || kill -TERM "$entry" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT INT TERM

mapping_pid=""
for _ in $(seq 1 60); do
  for proc in /proc/[0-9]*; do
    [[ -e "$proc/exe" ]] || continue
    if [[ "$(readlink -f "$proc/exe" 2>/dev/null || true)" == "$BIN" ]]; then
      mapping_pid=${proc##*/}
      break 2
    fi
  done
  sleep 0.5
done
test -n "$mapping_pid"
printf '%s\n' "$launch_pid" >"$RUN/launch_pid.txt"
printf '%s\n' "$mapping_pid" >"$RUN/mapping_pid.txt"

ros2 node info /laser_mapping >"$RUN/node_info.txt"
ros2 param dump /laser_mapping >"$RUN/parameters.yaml"
ros2 node list --no-daemon --spin-time 2 >"$RUN/nodes.txt"

setsid python3 /workspace/baseline_artifacts/scripts/monitor_process.py \
  --pid "$mapping_pid" --output "$RUN/process_metrics.csv" --interval 0.5 \
  >"$RUN/process_monitor.log" 2>&1 &
process_monitor_pid=$!
setsid python3 /workspace/baseline_artifacts/scripts/monitor_ros_latency.py \
  --output "$RUN/ros_latency.csv" --interval 0.5 >"$RUN/latency_monitor.log" 2>&1 &
latency_pid=$!
setsid ros2 bag record --storage mcap -o "$RUN/estimated_odometry" \
  /Odometry /tf /tf_static >"$RUN/bag_record.log" 2>&1 &
recorder_pid=$!
sleep 3

set +e
if [[ "$PLAY_LIMIT" == "full" ]]; then
  ros2 bag play "$BAG" --clock --rate "$PLAY_RATE" --delay 5 --topics /livox/lidar /livox/imu \
    >"$RUN/bag_play.log" 2>&1
  bag_rc=$?
else
  timeout --signal=INT --kill-after=10s "${PLAY_LIMIT}s" \
    ros2 bag play "$BAG" --clock --rate "$PLAY_RATE" --delay 5 --topics /livox/lidar /livox/imu \
    >"$RUN/bag_play.log" 2>&1
  bag_rc=$?
fi
set -e
if [[ "$PLAY_LIMIT" == "full" ]]; then
  test "$bag_rc" = "0"
else
  test "$bag_rc" = "124" -o "$bag_rc" = "0"
fi

drain_rc=0
if [[ "$PLAY_LIMIT" == "full" ]]; then
  set +e
  python3 /workspace/baseline_artifacts/scripts/wait_for_drain.py \
    --latency-csv "$RUN/ros_latency.csv" --output "$RUN/drain.json" --timeout 120 \
    --target-odom-stamp 1658138371.9247339
  drain_rc=$?
  set -e
else
  sleep 5
fi

cleanup
trap - EXIT INT TERM
set +e
wait "$recorder_pid"; recorder_rc=$?
wait "$latency_pid"; latency_rc=$?
wait "$process_monitor_pid"; process_monitor_rc=$?
wait "$launch_pid"; launch_rc=$?
set -e
printf 'bag_play=%s\nbag_record=%s\nlatency_monitor=%s\nprocess_monitor=%s\nlaunch=%s\ndrain=%s\n' \
  "$bag_rc" "$recorder_rc" "$latency_rc" "$process_monitor_rc" "$launch_rc" "$drain_rc" \
  >"$RUN/exit_codes.txt"

ros2 bag info "$RUN/estimated_odometry" >"$RUN/estimated_odometry_bag_info.txt"
python3 /workspace/baseline_artifacts/scripts/export_odometry.py \
  "$RUN/estimated_odometry" --output-prefix "$RUN/estimated"
sha256sum "$RUN/estimated.csv" "$RUN/estimated.tum" >"$RUN/trajectory_sha256.txt"
grep -E -i '(^|[^[:alpha:]])(nan|inf)([^[:alpha:]]|$)|segmentation fault|core dumped|terminate called' \
  "$RUN/fastlio.log" >"$RUN/error_scan.txt" || true

if [[ "$MODE" == "enabled" ]]; then
  python3 "$STAGE/scripts/augment_run_summary.py" "$RUN" \
    --run-id "$RUN_ID" --binary "$BIN" --source "$SOURCE" --dataset "$BAG" \
    --dataset-sha256 "$DATASET_SHA256"
  python3 "$STAGE/scripts/validate_lifecycle.py" "$RUN" >"$RUN/lifecycle_validation.log" 2>&1
else
  python3 "$STAGE/scripts/validate_lifecycle.py" "$RUN" --disabled >"$RUN/lifecycle_validation.log" 2>&1
fi

test "$drain_rc" = "0"
test ! -s "$RUN/error_scan.txt"
echo "B2 run passed: $RUN_ID ($MODE)"
