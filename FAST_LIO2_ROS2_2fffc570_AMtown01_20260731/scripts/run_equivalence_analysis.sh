#!/usr/bin/env bash
set -euo pipefail

BASE=/data/fastlio_baseline
OUT="$BASE/analysis/equivalence"
mkdir -p "$OUT"
python3 /workspace/baseline_artifacts/scripts/compare_trajectories.py \
  "$BASE/runs/b0_equivalence_02/estimated.csv" \
  "$BASE/runs/b1_equivalence_02/estimated.csv" \
  --output "$OUT/b0_b1_equivalence.json"
sha256sum "$OUT/b0_b1_equivalence.json" "$OUT/b0_b1_equivalence.csv" \
  >"$OUT/equivalence_sha256.txt"
test -s "$BASE/runs/b1_equivalence_01/frame_metrics.csv"
echo "B0/B1 equivalence analysis passed"
