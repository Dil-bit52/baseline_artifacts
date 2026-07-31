#!/usr/bin/env bash
set -euo pipefail

BASE=/data/fastlio_baseline
WS="$BASE/workspaces/b0"
BAG="$BASE/datasets/AMtown01_driver2"
CONFIG_DIR="$BASE/configs/smoke"
RUN="$BASE/runs/b0_smoke_01"
export ROS_DOMAIN_ID=47

test -d "$WS/install/fast_lio"
test -d "$BAG"
test -f "$CONFIG_DIR/baseline_smoke.yaml"
test ! -e "$RUN"
mkdir -p "$RUN"

set +u
source /opt/ros/humble/setup.bash
source "$WS/install/setup.bash"
set -u

cat >"$RUN/commands.txt" <<EOF
ROS_DOMAIN_ID=47 ros2 launch fast_lio mapping.launch.py config_path:=$CONFIG_DIR config_file:=baseline_smoke.yaml use_sim_time:=true rviz:=false
ROS_DOMAIN_ID=47 ros2 bag play $BAG --clock --rate 1.0 --topics /livox/lidar /livox/imu (stopped by timeout SIGINT after 120 wall seconds)
ROS_DOMAIN_ID=47 ros2 bag record --storage mcap -o $RUN/estimated_odometry /Odometry /tf /tf_static
EOF

setsid ros2 launch fast_lio mapping.launch.py \
  config_path:="$CONFIG_DIR" config_file:=baseline_smoke.yaml \
  use_sim_time:=true rviz:=false >"$RUN/fastlio.log" 2>&1 &
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
    exe=$(readlink -f "$proc/exe" 2>/dev/null || true)
    if [[ "$exe" == "$WS/install/fast_lio/lib/fast_lio/fastlio_mapping" ]]; then
      mapping_pid=${proc##*/}
      break 2
    fi
  done
  sleep 0.5
done
test -n "$mapping_pid"
test "$(readlink -f "/proc/$mapping_pid/exe")" = "$WS/install/fast_lio/lib/fast_lio/fastlio_mapping"
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
timeout --signal=INT --kill-after=10s 120s \
  ros2 bag play "$BAG" --clock --rate 1.0 --topics /livox/lidar /livox/imu \
  >"$RUN/bag_play.log" 2>&1
bag_rc=$?
set -e
bag_end_wall=$(date +%s.%N)
printf '%s\n' "$bag_end_wall" >"$RUN/bag_end_wall.txt"
test "$bag_rc" = "124" -o "$bag_rc" = "0"

sleep 3
odom_end_wall=$(date +%s.%N)
python3 - "$bag_end_wall" "$odom_end_wall" >"$RUN/drain_time.txt" <<'PY'
import sys
print(f"{float(sys.argv[2]) - float(sys.argv[1]):.6f}")
PY

cleanup
trap - EXIT INT TERM
set +e
wait "$recorder_pid"; recorder_rc=$?
wait "$latency_pid"; latency_rc=$?
wait "$process_monitor_pid"; process_monitor_rc=$?
wait "$launch_pid"; launch_rc=$?
set -e
printf 'bag_play=%s\nbag_record=%s\nlatency_monitor=%s\nprocess_monitor=%s\nlaunch=%s\n' \
  "$bag_rc" "$recorder_rc" "$latency_rc" "$process_monitor_rc" "$launch_rc" >"$RUN/exit_codes.txt"

ros2 bag info "$RUN/estimated_odometry" >"$RUN/estimated_odometry_bag_info.txt"
python3 /workspace/baseline_artifacts/scripts/export_odometry.py \
  "$RUN/estimated_odometry" --output-prefix "$RUN/estimated"
sha256sum "$RUN/estimated.csv" "$RUN/estimated.tum" >"$RUN/trajectory_sha256.txt"
grep -E -i '(^|[^[:alpha:]])(nan|inf)([^[:alpha:]]|$)|segmentation fault|core dumped|terminate called' "$RUN/fastlio.log" \
  >"$RUN/error_scan.txt" || true
test ! -s "$RUN/error_scan.txt"

echo "B0 smoke run passed"
