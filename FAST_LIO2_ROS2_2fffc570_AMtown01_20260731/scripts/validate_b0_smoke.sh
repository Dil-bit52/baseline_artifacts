#!/usr/bin/env bash
set -euo pipefail

RUN=/data/fastlio_baseline/runs/b0_smoke_01
set +u
source /opt/ros/humble/setup.bash
source /data/fastlio_baseline/workspaces/b0/install/setup.bash
set -u
grep -E -i '(^|[^[:alpha:]])(nan|inf)([^[:alpha:]]|$)|segmentation fault|core dumped|terminate called' \
  "$RUN/fastlio.log" >"$RUN/error_scan.txt" || true
test ! -s "$RUN/error_scan.txt"
python3 /workspace/baseline_artifacts/scripts/export_odometry.py \
  "$RUN/estimated_odometry" --output-prefix "$RUN/estimated"
sha256sum "$RUN/estimated.csv" "$RUN/estimated.tum" >"$RUN/trajectory_sha256.txt"
echo "B0 smoke validation passed"
