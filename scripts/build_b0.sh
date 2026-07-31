#!/usr/bin/env bash
set -o pipefail

BASE=/data/fastlio_baseline
WS="$BASE/workspaces/b0"

source /opt/ros/humble/setup.bash
cd "$WS"

build_start_ns=$(date +%s%N)

colcon \
  --log-base log \
  build \
  --base-paths src \
  --build-base build \
  --install-base install \
  --packages-up-to fast_lio \
  --event-handlers console_direct+ \
  --cmake-args \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
    -DROS_EDITION=ROS2 \
    -DDISTRO_ROS=humble \
  2>&1 | tee colcon_build.log

build_rc=${PIPESTATUS[0]}
build_end_ns=$(date +%s%N)
python3 - "$build_start_ns" "$build_end_ns" >build_time.txt <<'PY'
import sys
start, end = map(int, sys.argv[1:])
print("measurement_method=wall_clock_fallback")
print("reason=/usr/bin/time unavailable")
print(f"elapsed_seconds={(end - start) / 1e9:.6f}")
PY
printf '%s\n' "$build_rc" >build_exit_code.txt
exit "$build_rc"
