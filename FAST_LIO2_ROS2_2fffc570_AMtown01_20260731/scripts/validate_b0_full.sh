#!/usr/bin/env bash
set -euo pipefail

RUN=/data/fastlio_baseline/runs/b0_full_01
set +u
source /opt/ros/humble/setup.bash
source /data/fastlio_baseline/workspaces/b0/install/setup.bash
set -u
python3 /workspace/baseline_artifacts/scripts/export_odometry.py \
  "$RUN/estimated_odometry" --output-prefix "$RUN/estimated"
grep -E -i '(^|[^[:alpha:]])(nan|inf)([^[:alpha:]]|$)|segmentation fault|core dumped|terminate called' \
  "$RUN/fastlio.log" >"$RUN/error_scan.txt" || true
test ! -s "$RUN/error_scan.txt"
test -s "$RUN/registered_scan_aggregation.pcd"
sha256sum "$RUN/registered_scan_aggregation.pcd" >"$RUN/map_sha256.txt"
python3 - "$RUN" /data/fastlio_baseline/datasets/inspection/tail_1342s/tail_validity.csv <<'PY'
import csv
import json
from pathlib import Path
import sys
run = Path(sys.argv[1])
tail_csv = Path(sys.argv[2])
trajectory = json.loads((run / "estimated_summary.json").read_text(encoding="utf-8"))
with tail_csv.open(newline="", encoding="utf-8") as stream:
    rows = list(csv.DictReader(stream))
last_usable = max(
    (float(row["stamp"]) for row in rows if int(row["approx_filtered_points_over_4m"]) >= 5),
    default=None,
)
later = [row for row in rows if last_usable is not None and float(row["stamp"]) > last_usable]
explained = bool(later) and all(int(row["approx_filtered_points_over_4m"]) < 5 for row in later)
accepted = (
    trajectory["all_values_finite"]
    and trajectory["timestamps_strictly_increasing"]
    and last_usable is not None
    and trajectory["end_stamp"] >= last_usable
    and explained
)
result = {
    "accepted": accepted,
    "raw_drain_exit_code": 2,
    "raw_drain_timeout_preserved": True,
    "reason": "bag tail after the last odometry contains only scans with fewer than five approximate usable points",
    "last_usable_lidar_stamp": last_usable,
    "last_odometry_stamp": trajectory["end_stamp"],
    "tail_frames_after_last_usable": len(later),
    "all_later_tail_frames_below_five_points": explained,
}
(run / "functional_acceptance.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
if not accepted:
    raise SystemExit(2)
PY
echo "B0 full outputs validated; drain disposition is documented separately"
