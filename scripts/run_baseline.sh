#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 <b0|b1> <run_id> <smoke|performance|map_export|visualization> <full|seconds> <save_map:true|false> [rviz:true|false]" >&2
}

[[ $# -eq 5 || $# -eq 6 ]] || { usage; exit 2; }
VARIANT=$1
RUN_ID=$2
CONFIG_KIND=$3
PLAY_LIMIT=$4
SAVE_MAP=$5
LAUNCH_RVIZ=${6:-false}
[[ "$VARIANT" == "b0" || "$VARIANT" == "b1" ]] || { usage; exit 2; }
[[ "$SAVE_MAP" == "true" || "$SAVE_MAP" == "false" ]] || { usage; exit 2; }
[[ "$LAUNCH_RVIZ" == "true" || "$LAUNCH_RVIZ" == "false" ]] || { usage; exit 2; }

BASE=/data/fastlio_baseline
WS="$BASE/workspaces/$VARIANT"
BAG="$BASE/datasets/AMtown01_driver2"
RUN="$BASE/runs/$RUN_ID"
CONFIG_TEMPLATE="$BASE/configs/$CONFIG_KIND/baseline_${CONFIG_KIND}.yaml"
BIN="$WS/install/fast_lio/lib/fast_lio/fastlio_mapping"
export ROS_DOMAIN_ID=47
export FASTLIO_METRICS_CSV="$RUN/frame_metrics.csv"

test -x "$BIN"
test -d "$BAG"
test -f "$CONFIG_TEMPLATE"
test ! -e "$RUN"
free_bytes=$(df -B1 /data | awk 'NR==2 {print $4}')
test "$free_bytes" -gt $((30 * 1024 * 1024 * 1024))
mkdir -p "$RUN"
cp "$CONFIG_TEMPLATE" "$RUN/config.yaml"
if [[ "$SAVE_MAP" == "true" ]]; then
  python3 - "$RUN/config.yaml" "$RUN/registered_scan_aggregation.pcd" <<'PY'
from pathlib import Path
import sys
path, output = map(Path, sys.argv[1:])
text = path.read_text(encoding="utf-8")
lines = text.splitlines()
for index, line in enumerate(lines):
    if line.lstrip().startswith("map_file_path:"):
        prefix = line[: len(line) - len(line.lstrip())]
        lines[index] = f'{prefix}map_file_path: "{output}"'
        break
else:
    raise SystemExit("map_file_path missing")
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
fi
sha256sum "$RUN/config.yaml" >"$RUN/config.sha256"

set +u
source /opt/ros/humble/setup.bash
source "$WS/install/setup.bash"
set -u

nodes_before=$(ros2 node list --no-daemon --spin-time 2)
if [[ -n "$nodes_before" ]]; then
  printf '%s\n' "$nodes_before" >"$RUN/nodes_before.txt"
  echo "ROS domain 47 is not empty" >&2
  exit 4
fi

{
  echo "variant=$VARIANT"
  echo "run_id=$RUN_ID"
  echo "ROS_DOMAIN_ID=$ROS_DOMAIN_ID"
  echo "launch=ros2 launch fast_lio mapping.launch.py config_path:=$RUN config_file:=config.yaml use_sim_time:=true rviz:=$LAUNCH_RVIZ"
  echo "play=ros2 bag play $BAG --clock --rate 1.0 --delay 5 --topics /livox/lidar /livox/imu"
  echo "record=ros2 bag record --storage mcap -o $RUN/estimated_odometry /Odometry /tf /tf_static"
} >"$RUN/commands.txt"

setsid ros2 launch fast_lio mapping.launch.py \
  config_path:="$RUN" config_file:=config.yaml use_sim_time:=true rviz:="$LAUNCH_RVIZ" \
  >"$RUN/fastlio.log" 2>&1 &
launch_pid=$!
recorder_pid=""
latency_pid=""
process_monitor_pid=""

cleanup() {
  set +e
  for entry in "$recorder_pid" "$latency_pid" "$process_monitor_pid" "$launch_pid"; do
    if [[ -n "$entry" ]] && kill -0 "$entry" 2>/dev/null; then
      kill -INT -- "-$entry" 2>/dev/null || kill -INT "$entry" 2>/dev/null || true
    fi
  done
  sleep 2
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
test "$(readlink -f "/proc/$mapping_pid/exe")" = "$BIN"
printf '%s\n' "$launch_pid" >"$RUN/launch_pid.txt"
printf '%s\n' "$mapping_pid" >"$RUN/mapping_pid.txt"

ros2 node info /laser_mapping >"$RUN/node_info.txt"
ros2 param dump /laser_mapping >"$RUN/parameters.yaml"
timeout 5s ros2 topic list -t --no-daemon --spin-time 2 >"$RUN/topics.txt" || true
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
  ros2 bag play "$BAG" --clock --rate 1.0 --delay 5 --topics /livox/lidar /livox/imu \
    >"$RUN/bag_play.log" 2>&1
  bag_rc=$?
else
  timeout --signal=INT --kill-after=10s "${PLAY_LIMIT}s" \
    ros2 bag play "$BAG" --clock --rate 1.0 --delay 5 --topics /livox/lidar /livox/imu \
    >"$RUN/bag_play.log" 2>&1
  bag_rc=$?
fi
set -e
bag_end_monotonic=$(python3 -c 'import time; print(time.monotonic())')
printf '%s\n' "$bag_end_monotonic" >"$RUN/bag_end_monotonic.txt"
if [[ "$PLAY_LIMIT" == "full" ]]; then
  test "$bag_rc" = "0"
else
  test "$bag_rc" = "124" -o "$bag_rc" = "0"
fi

set +e
drain_args=(--latency-csv "$RUN/ros_latency.csv" --output "$RUN/drain.json" --timeout 120)
if [[ "$PLAY_LIMIT" == "full" ]]; then
  drain_args+=(--target-odom-stamp 1658138371.9247339)
fi
python3 /workspace/baseline_artifacts/scripts/wait_for_drain.py "${drain_args[@]}"
drain_rc=$?
set -e

map_rc="N/A"
if [[ "$SAVE_MAP" == "true" ]]; then
  set +e
  timeout 300s ros2 service call /map_save std_srvs/srv/Trigger '{}' \
    >"$RUN/map_save_service.txt" 2>&1
  map_rc=$?
  set -e
fi

cleanup
trap - EXIT INT TERM
set +e
wait "$recorder_pid"; recorder_rc=$?
wait "$latency_pid"; latency_rc=$?
wait "$process_monitor_pid"; process_monitor_rc=$?
wait "$launch_pid"; launch_rc=$?
set -e
printf 'bag_play=%s\nbag_record=%s\nlatency_monitor=%s\nprocess_monitor=%s\nlaunch=%s\ndrain=%s\nmap_save=%s\n' \
  "$bag_rc" "$recorder_rc" "$latency_rc" "$process_monitor_rc" "$launch_rc" "$drain_rc" "$map_rc" \
  >"$RUN/exit_codes.txt"

ros2 bag info "$RUN/estimated_odometry" >"$RUN/estimated_odometry_bag_info.txt"
python3 /workspace/baseline_artifacts/scripts/export_odometry.py \
  "$RUN/estimated_odometry" --output-prefix "$RUN/estimated"
sha256sum "$RUN/estimated.csv" "$RUN/estimated.tum" >"$RUN/trajectory_sha256.txt"
grep -E -i '(^|[^[:alpha:]])(nan|inf)([^[:alpha:]]|$)|segmentation fault|core dumped|terminate called' \
  "$RUN/fastlio.log" >"$RUN/error_scan.txt" || true

python3 - "$RUN" "$VARIANT" "$RUN_ID" "$bag_rc" "$drain_rc" "$map_rc" <<'PY'
import hashlib
import json
from pathlib import Path
import sys
run = Path(sys.argv[1])
def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()
manifest = {
    'variant': sys.argv[2],
    'run_id': sys.argv[3],
    'bag_play_exit_code': int(sys.argv[4]),
    'drain_exit_code': int(sys.argv[5]),
    'map_save_exit_code': sys.argv[6],
    'config_sha256': sha(run / 'config.yaml'),
    'trajectory_csv_sha256': sha(run / 'estimated.csv'),
    'trajectory_tum_sha256': sha(run / 'estimated.tum'),
}
(run / 'run_manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding='utf-8')
PY

test "$drain_rc" = "0"
test ! -s "$RUN/error_scan.txt"
if [[ "$SAVE_MAP" == "true" ]]; then
  test "$map_rc" = "0"
  test -s "$RUN/registered_scan_aggregation.pcd"
  sha256sum "$RUN/registered_scan_aggregation.pcd" >"$RUN/map_sha256.txt"
fi

echo "Baseline run passed: $RUN_ID"
