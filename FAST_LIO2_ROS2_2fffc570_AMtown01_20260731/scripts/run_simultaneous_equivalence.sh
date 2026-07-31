#!/usr/bin/env bash
set -euo pipefail

BASE=/data/fastlio_baseline
RUN="$BASE/runs/equivalence_simultaneous_03"
BAG="$BASE/datasets/AMtown01_driver2"
CONFIG="$BASE/configs/performance/baseline_performance.yaml"
B0_BIN="$BASE/workspaces/b0/install/fast_lio/lib/fast_lio/fastlio_mapping"
B1_BIN="$BASE/workspaces/b1/install/fast_lio/lib/fast_lio/fastlio_mapping"
export ROS_DOMAIN_ID=49
test ! -e "$RUN"
test -x "$B0_BIN"
test -x "$B1_BIN"
mkdir -p "$RUN"
cp "$CONFIG" "$RUN/config.yaml"

cat >"$RUN/commands.txt" <<EOF
B0: OMP_THREAD_LIMIT=1 $B0_BIN --ros-args --params-file $RUN/config.yaml -p use_sim_time:=true -r __node:=laser_mapping_b0 -r /Odometry:=/b0/Odometry -r /tf:=/b0/tf -r /tf_static:=/b0/tf_static -r /map_save:=/b0/map_save
B1: OMP_THREAD_LIMIT=1 $B1_BIN --ros-args --params-file $RUN/config.yaml -p use_sim_time:=true -r __node:=laser_mapping_b1 -r /Odometry:=/b1/Odometry -r /tf:=/b1/tf -r /tf_static:=/b1/tf_static -r /map_save:=/b1/map_save
PLAY: ros2 bag play $BAG --clock --rate 0.1 --delay 5 --topics /livox/lidar /livox/imu (180 wall seconds)
EOF

setsid bash -lc "source /opt/ros/humble/setup.bash; source $BASE/workspaces/b0/install/setup.bash; export ROS_DOMAIN_ID=49; export OMP_THREAD_LIMIT=1; exec $B0_BIN --ros-args --params-file $RUN/config.yaml -p use_sim_time:=true -r __node:=laser_mapping_b0 -r /Odometry:=/b0/Odometry -r /tf:=/b0/tf -r /tf_static:=/b0/tf_static -r /map_save:=/b0/map_save" \
  >"$RUN/b0.log" 2>&1 &
b0_pid=$!
setsid bash -lc "source /opt/ros/humble/setup.bash; source $BASE/workspaces/b1/install/setup.bash; export ROS_DOMAIN_ID=49; export OMP_THREAD_LIMIT=1; export FASTLIO_METRICS_CSV=$RUN/frame_metrics.csv; exec $B1_BIN --ros-args --params-file $RUN/config.yaml -p use_sim_time:=true -r __node:=laser_mapping_b1 -r /Odometry:=/b1/Odometry -r /tf:=/b1/tf -r /tf_static:=/b1/tf_static -r /map_save:=/b1/map_save" \
  >"$RUN/b1.log" 2>&1 &
b1_pid=$!
record_pid=""

cleanup() {
  set +e
  for pid in "$record_pid" "$b0_pid" "$b1_pid"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill -INT -- "-$pid" 2>/dev/null || kill -INT "$pid" 2>/dev/null || true
    fi
  done
  sleep 2
  for pid in "$record_pid" "$b0_pid" "$b1_pid"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT INT TERM

set +u
source /opt/ros/humble/setup.bash
source "$BASE/workspaces/b1/install/setup.bash"
set -u
for _ in $(seq 1 40); do
  nodes=$(ros2 node list --no-daemon --spin-time 1 || true)
  if grep -qx /laser_mapping_b0 <<<"$nodes" && grep -qx /laser_mapping_b1 <<<"$nodes"; then break; fi
  sleep 0.5
done
grep -qx /laser_mapping_b0 <<<"$nodes"
grep -qx /laser_mapping_b1 <<<"$nodes"
printf '%s\n' "$nodes" >"$RUN/nodes.txt"

setsid ros2 bag record --storage mcap -o "$RUN/estimated_odometry" \
  /b0/Odometry /b1/Odometry >"$RUN/bag_record.log" 2>&1 &
record_pid=$!
sleep 3
set +e
timeout --signal=INT --kill-after=10s 180s \
  ros2 bag play "$BAG" --clock --rate 0.1 --delay 5 --topics /livox/lidar /livox/imu \
  >"$RUN/bag_play.log" 2>&1
bag_rc=$?
set -e
test "$bag_rc" = "124" -o "$bag_rc" = "0"
sleep 5
cleanup
trap - EXIT INT TERM
set +e
wait "$record_pid"; record_rc=$?
wait "$b0_pid"; b0_rc=$?
wait "$b1_pid"; b1_rc=$?
set -e
printf 'bag_play=%s\nbag_record=%s\nb0=%s\nb1=%s\n' "$bag_rc" "$record_rc" "$b0_rc" "$b1_rc" \
  >"$RUN/exit_codes.txt"

python3 /workspace/baseline_artifacts/scripts/export_odometry.py \
  "$RUN/estimated_odometry" --topic /b0/Odometry --output-prefix "$RUN/b0_estimated"
python3 /workspace/baseline_artifacts/scripts/export_odometry.py \
  "$RUN/estimated_odometry" --topic /b1/Odometry --output-prefix "$RUN/b1_estimated"
python3 /workspace/baseline_artifacts/scripts/compare_trajectories.py \
  "$RUN/b0_estimated.csv" "$RUN/b1_estimated.csv" --output "$RUN/equivalence.json"
sha256sum "$RUN/b0_estimated.csv" "$RUN/b1_estimated.csv" "$RUN/equivalence.json" \
  >"$RUN/essential_sha256.txt"
echo "Simultaneous B0/B1 equivalence passed"
