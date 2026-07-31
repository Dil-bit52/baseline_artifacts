#!/usr/bin/env bash
set -euo pipefail

BASE=/data/fastlio_baseline
ARCHIVE=/workspace/baseline_artifacts
B0="$BASE/source/b0_vanilla"

cp "$B0/config/avia.yaml" "$BASE/configs/original/avia.yaml"
cp "$ARCHIVE/configs/baseline_smoke.yaml" "$BASE/configs/smoke/baseline_smoke.yaml"
cp "$ARCHIVE/configs/baseline_performance.yaml" "$BASE/configs/performance/baseline_performance.yaml"
cp "$ARCHIVE/configs/baseline_map_export.yaml" "$BASE/configs/map_export/baseline_map_export.yaml"
cp "$ARCHIVE/configs/baseline_visualization.yaml" "$BASE/configs/visualization/baseline_visualization.yaml"

for item in \
  smoke/baseline_smoke.yaml \
  performance/baseline_performance.yaml \
  map_export/baseline_map_export.yaml \
  visualization/baseline_visualization.yaml; do
  name=${item//\//_}
  diff -u "$BASE/configs/original/avia.yaml" "$BASE/configs/$item" \
    >"$BASE/configs/${name}.diff" || true
done

find "$BASE/configs" -type f -name '*.yaml' -print0 | sort -z | xargs -0 sha256sum \
  >"$BASE/configs/configs_sha256.txt"
echo "Staged original and four experiment configurations"
