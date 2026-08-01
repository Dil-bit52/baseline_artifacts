#!/usr/bin/env bash
set -euo pipefail

RUN_ID=${1:-equivalence_b1_b2_01}
WALL_SECONDS=${2:-180}
ROS_DOMAIN=${3:-59}
BASE=/data/fastlio_baseline
STAGE=/workspace/stage2_artifacts
B2_WS=/workspace/stage2_workspaces/b2
RUN="$STAGE/raw/runs/$RUN_ID"
BAG="$BASE/datasets/AMtown01_driver2"
B1_BIN="$BASE/workspaces/b1/install/fast_lio/lib/fast_lio/fastlio_mapping"
B2_BIN="$B2_WS/install/fast_lio/lib/fast_lio/fastlio_mapping"
B1_CONFIG="$BASE/configs/performance/baseline_performance.yaml"
DATASET_SHA256=6f3c85f54982d88d1dd2707815922e5a77fa7d64a787a608ac43d6a70f819586

test ! -e "$RUN"
test -x "$B1_BIN"
test -x "$B2_BIN"
mkdir -p "$RUN"
cp "$B1_CONFIG" "$RUN/b1_config.yaml"
cp "$STAGE/config/b2_lifecycle.yaml" "$RUN/b2_config.yaml"
python3 - "$RUN/b2_config.yaml" "$RUN/lifecycle" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
path.write_text(text.replace("__OUTPUT_DIRECTORY__", sys.argv[2]), encoding="utf-8")
PY

export ROS_DOMAIN_ID="$ROS_DOMAIN"
nodes_before=$(bash -lc "source /opt/ros/humble/setup.bash; ros2 node list --no-daemon --spin-time 2" || true)
if [[ -n "$nodes_before" ]]; then
  printf '%s\n' "$nodes_before" >"$RUN/nodes_before.txt"
  echo "ROS domain $ROS_DOMAIN is not empty" >&2
  exit 4
fi

{
  echo "B1: OMP_THREAD_LIMIT=1 $B1_BIN --ros-args --params-file $RUN/b1_config.yaml -p use_sim_time:=true -r __node:=laser_mapping_b1 -r /Odometry:=/b1/Odometry"
  echo "B2: OMP_THREAD_LIMIT=1 $B2_BIN --ros-args --params-file $RUN/b2_config.yaml -p use_sim_time:=true -r __node:=laser_mapping_b2 -r /Odometry:=/b2/Odometry"
  echo "PLAY: ros2 bag play $BAG --clock --rate 0.1 --delay 5 --topics /livox/lidar /livox/imu ($WALL_SECONDS wall seconds)"
} >"$RUN/commands.txt"

setsid bash -lc "source /opt/ros/humble/setup.bash; source $BASE/workspaces/b1/install/setup.bash; export ROS_DOMAIN_ID=$ROS_DOMAIN; export OMP_THREAD_LIMIT=1; export FASTLIO_METRICS_CSV=$RUN/b1_frame_metrics.csv; exec $B1_BIN --ros-args --params-file $RUN/b1_config.yaml -p use_sim_time:=true -r __node:=laser_mapping_b1 -r /Odometry:=/b1/Odometry -r /tf:=/b1/tf -r /tf_static:=/b1/tf_static -r /map_save:=/b1/map_save" \
  >"$RUN/b1.log" 2>&1 &
b1_pid=$!
setsid bash -lc "source /opt/ros/humble/setup.bash; source $B2_WS/install/setup.bash; export ROS_DOMAIN_ID=$ROS_DOMAIN; export OMP_THREAD_LIMIT=1; export FASTLIO_METRICS_CSV=$RUN/b2_frame_metrics.csv; exec $B2_BIN --ros-args --params-file $RUN/b2_config.yaml -p use_sim_time:=true -r __node:=laser_mapping_b2 -r /Odometry:=/b2/Odometry -r /tf:=/b2/tf -r /tf_static:=/b2/tf_static -r /map_save:=/b2/map_save" \
  >"$RUN/b2.log" 2>&1 &
b2_pid=$!
record_pid=""

cleanup() {
  set +e
  for pid in "$record_pid" "$b1_pid" "$b2_pid"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill -INT -- "-$pid" 2>/dev/null || kill -INT "$pid" 2>/dev/null || true
    fi
  done
  sleep 2
  for pid in "$record_pid" "$b1_pid" "$b2_pid"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT INT TERM

set +u
source /opt/ros/humble/setup.bash
source "$B2_WS/install/setup.bash"
set -u
for _ in $(seq 1 40); do
  nodes=$(ros2 node list --no-daemon --spin-time 1 || true)
  if grep -qx /laser_mapping_b1 <<<"$nodes" && grep -qx /laser_mapping_b2 <<<"$nodes"; then break; fi
  sleep 0.5
done
grep -qx /laser_mapping_b1 <<<"$nodes"
grep -qx /laser_mapping_b2 <<<"$nodes"
printf '%s\n' "$nodes" >"$RUN/nodes.txt"

setsid ros2 bag record --storage mcap -o "$RUN/estimated_odometry" \
  /b1/Odometry /b2/Odometry >"$RUN/bag_record.log" 2>&1 &
record_pid=$!
sleep 3
set +e
timeout --signal=INT --kill-after=10s "${WALL_SECONDS}s" \
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
wait "$b1_pid"; b1_rc=$?
wait "$b2_pid"; b2_rc=$?
set -e
printf 'bag_play=%s\nbag_record=%s\nb1=%s\nb2=%s\n' \
  "$bag_rc" "$record_rc" "$b1_rc" "$b2_rc" >"$RUN/exit_codes.txt"

python3 "$STAGE/scripts/augment_run_summary.py" "$RUN" \
  --run-id "$RUN_ID" --binary "$B2_BIN" --source "$B2_WS/src/fast_lio" --dataset "$BAG" \
  --dataset-sha256 "$DATASET_SHA256"
python3 "$STAGE/scripts/validate_lifecycle.py" "$RUN" >"$RUN/lifecycle_validation.log" 2>&1
python3 /workspace/baseline_artifacts/scripts/export_odometry.py \
  "$RUN/estimated_odometry" --topic /b1/Odometry --output-prefix "$RUN/b1_estimated"
python3 /workspace/baseline_artifacts/scripts/export_odometry.py \
  "$RUN/estimated_odometry" --topic /b2/Odometry --output-prefix "$RUN/b2_estimated"
python3 /workspace/baseline_artifacts/scripts/compare_trajectories.py \
  "$RUN/b1_estimated.csv" "$RUN/b2_estimated.csv" --output "$RUN/equivalence.json"
grep -E -i '(^|[^[:alpha:]])(nan|inf)([^[:alpha:]]|$)|segmentation fault|core dumped|terminate called' \
  "$RUN/b1.log" "$RUN/b2.log" >"$RUN/error_scan.txt" || true
test ! -s "$RUN/error_scan.txt"
sha256sum "$RUN/b1_estimated.csv" "$RUN/b2_estimated.csv" "$RUN/equivalence.json" \
  >"$RUN/essential_sha256.txt"
echo "Controlled B1/B2 equivalence passed: $RUN_ID"
