#!/usr/bin/env bash
set -euo pipefail

BASE=/data/fastlio_baseline
WS="$BASE/workspaces/b0"
SOURCE=/workspace/datasets/AMtown01_driver2
DEST="$BASE/datasets/AMtown01_driver2"
OUT="$BASE/datasets/inspection"
MIN_FREE_AFTER_GB=30
mkdir -p "$OUT"

set +u
source /opt/ros/humble/setup.bash
source "$WS/install/setup.bash"
set -u

ros2 bag info "$SOURCE" >"$OUT/ros2_bag_info_source.txt"
ros2 interface show livox_ros_driver2/msg/CustomMsg >"$OUT/custom_msg_definition.txt"
ros2 interface show livox_ros_driver2/msg/CustomPoint >"$OUT/custom_point_definition.txt"

source_bytes=$(du -sb "$SOURCE" | awk '{print $1}')
free_bytes=$(df -B1 /data | awk 'NR==2 {print $4}')
predicted_remaining=$((free_bytes - source_bytes))
minimum_remaining=$((MIN_FREE_AFTER_GB * 1024 * 1024 * 1024))
{
  echo "source_bytes=$source_bytes"
  echo "free_before_bytes=$free_bytes"
  echo "predicted_free_after_copy_bytes=$predicted_remaining"
  echo "minimum_free_after_bytes=$minimum_remaining"
} >"$OUT/disk_precheck.txt"
if (( predicted_remaining < minimum_remaining )); then
  echo "Insufficient free space after dataset copy" >&2
  exit 3
fi

find "$SOURCE" -maxdepth 1 -type f -printf '%f,%s\n' | sort >"$OUT/source_sizes.csv"
while IFS= read -r -d '' file; do
  relative=${file#"$SOURCE"/}
  size=$(stat -c %s "$file")
  hash=$(sha256sum "$file" | awk '{print $1}')
  printf '%s,%s,%s\n' "$relative" "$size" "$hash"
done < <(find "$SOURCE" -maxdepth 1 -type f -print0 | sort -z) \
  >"$OUT/source_files_sha256.csv"

if [[ ! -e "$DEST" ]]; then
  cp -a --reflink=auto --sparse=always "$SOURCE" "$DEST"
fi

while IFS= read -r -d '' file; do
  relative=${file#"$DEST"/}
  size=$(stat -c %s "$file")
  hash=$(sha256sum "$file" | awk '{print $1}')
  printf '%s,%s,%s\n' "$relative" "$size" "$hash"
done < <(find "$DEST" -maxdepth 1 -type f -print0 | sort -z) \
  >"$OUT/staged_files_sha256.csv"

cmp "$OUT/source_files_sha256.csv" "$OUT/staged_files_sha256.csv"
ros2 bag info "$DEST" >"$OUT/ros2_bag_info_staged.txt"
df -B1 /data >"$OUT/disk_after.txt"

echo "Dataset staged and source/destination SHA256 manifests match"
