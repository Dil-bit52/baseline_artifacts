#!/usr/bin/env bash
set -euo pipefail

BASE=/data/fastlio_baseline
ART=/workspace/baseline_artifacts
BASELINE_ID=FAST_LIO2_ROS2_2fffc570_AMtown01_20260731
TARGET="$ART/$BASELINE_ID"

if [[ -e "$TARGET" ]]; then
  echo "refusing to overwrite existing archive: $TARGET" >&2
  exit 2
fi

mkdir -p "$TARGET"/{analysis,build/{b0,b1},dataset,manifest,report,runs,source,configs,scripts,docker_stats}

cp -a "$ART/report/." "$TARGET/report/"
cp -a "$ART/analysis/csv" "$ART/analysis/plots" "$TARGET/analysis/"
cp -a "$ART/analysis/FAST_LIO2_baseline_results.xlsx" "$TARGET/analysis/"
cp -a "$ART/configs/." "$TARGET/configs/"
cp -a "$ART/scripts/." "$TARGET/scripts/"
cp -a "$ART/instrumentation.patch" "$ART/TASK_STATUS.md" "$TARGET/"
cp -a "$ART/public_redacted" "$ART/private" "$TARGET/"
cp -a "$ART/visualization_01_desktop.png" "$TARGET/report/rviz_failure_desktop_evidence.png"

cp -a "$BASE/datasets/inspection/." "$TARGET/dataset/"
cp -a "$BASE/datasets/AMtown01_driver2/metadata.yaml" "$TARGET/dataset/metadata.yaml"
cp -a "$BASE/configs/configs_sha256.txt" "$TARGET/configs/"

for variant in b0 b1; do
  cp -a "$BASE/workspaces/$variant/build_acceptance" "$TARGET/build/$variant/"
  cp -a "$BASE/workspaces/$variant/build_exit_code.txt" \
        "$BASE/workspaces/$variant/build_time.txt" \
        "$BASE/workspaces/$variant/colcon_build.log" \
        "$BASE/workspaces/$variant/source_layout.txt" \
        "$BASE/workspaces/$variant/log" \
        "$TARGET/build/$variant/"
done

cp -a "$BASE/source/"*.txt "$TARGET/source/"
git -C "$BASE/source/b0_vanilla" bundle create "$TARGET/source/b0_fastlio.bundle" --all
git -C "$BASE/source/b0_vanilla/include/ikd-Tree" bundle create "$TARGET/source/ikd_tree.bundle" --all
git -C "$BASE/source/b1_instrumented" bundle create "$TARGET/source/b1_fastlio.bundle" --all
git -C "$BASE/source/livox_ros_driver2" bundle create "$TARGET/source/livox_ros_driver2.bundle" --all
git -C "$BASE/source/Livox-SDK2" bundle create "$TARGET/source/Livox-SDK2.bundle" --all

for run_id in \
  b0_smoke_01 b0_full_01 equivalence_simultaneous_01 equivalence_simultaneous_02 \
  equivalence_simultaneous_03 warmup_01 performance_01 performance_02 performance_03 \
  map_export_01 visualization_01; do
  cp -a "$BASE/runs/$run_id" "$TARGET/runs/"
done

for run_id in warmup_01 performance_01 performance_02 performance_03 map_export_01 visualization_01; do
  cp -a "$ART/docker_stats/$run_id.csv" "$TARGET/docker_stats/"
done

cat >"$TARGET/README.md" <<'EOF'
# FAST-LIO2 ROS2 frozen baseline archive

The 33 GB source dataset is intentionally not duplicated here.  Its staged path is
`/data/fastlio_baseline/datasets/AMtown01_driver2`; file hashes and rosbag metadata
are under `dataset/`.  B0 and B1 source histories are stored as Git bundles.  Large
PCD and low-bandwidth output bags are retained under their immutable run IDs.

`private/` contains raw local environment evidence and must not be published.
Use only `public_redacted/` in papers, slides, or public repositories.
EOF

echo "$TARGET"
