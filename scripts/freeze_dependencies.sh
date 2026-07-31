#!/usr/bin/env bash
set -euo pipefail

BASE=/data/fastlio_baseline
ARCHIVE=/workspace/baseline_artifacts
STATE="$ARCHIVE/private/source_state"
DRIVER_ORIGINAL=/workspace/src/1_drivers/livox_ros_driver2
SDK_ORIGINAL=/workspace/src/1_drivers/Livox-SDK2
DRIVER="$BASE/source/livox_ros_driver2"
SDK="$BASE/source/Livox-SDK2"
DRIVER_COMMIT=13eb05e4e6dd7a765b934d0c5fd6236676a57b49
SDK_COMMIT=22d98dcd4672953fbc96d6bc9f1be7a1c0cfef9e

mkdir -p "$STATE" "$BASE/workspaces/b0/src"

for item in "driver:$DRIVER_ORIGINAL" "sdk:$SDK_ORIGINAL"; do
  name=${item%%:*}
  path=${item#*:}
  git -C "$path" remote -v >"$STATE/${name}_remotes.txt"
  git -C "$path" branch --show-current >"$STATE/${name}_branch.txt"
  git -C "$path" rev-parse HEAD >"$STATE/${name}_head.txt"
  git -C "$path" status --porcelain=v2 >"$STATE/${name}_status_porcelain_v2.txt"
  git -C "$path" diff --binary >"$STATE/${name}_worktree.patch"
  git -C "$path" diff --cached --binary >"$STATE/${name}_index.patch"
  git -C "$path" ls-files --others --exclude-standard >"$STATE/${name}_untracked.txt"
  git -C "$path" submodule status --recursive >"$STATE/${name}_submodules.txt" || true
done

if [[ ! -e "$DRIVER" ]]; then
  git clone --no-hardlinks "$DRIVER_ORIGINAL" "$DRIVER"
  git -C "$DRIVER" checkout --detach "$DRIVER_COMMIT"
fi
if [[ ! -e "$SDK" ]]; then
  git clone --no-hardlinks "$SDK_ORIGINAL" "$SDK"
  git -C "$SDK" checkout --detach "$SDK_COMMIT"
fi

test "$(git -C "$DRIVER" rev-parse HEAD)" = "$DRIVER_COMMIT"
test "$(git -C "$SDK" rev-parse HEAD)" = "$SDK_COMMIT"
test -z "$(git -C "$DRIVER" status --porcelain=v2)"
test -z "$(git -C "$SDK" status --porcelain=v2)"

git -C "$DRIVER" archive --format=tar HEAD | sha256sum >"$BASE/source/livox_ros_driver2_archive.sha256"
git -C "$SDK" archive --format=tar HEAD | sha256sum >"$BASE/source/Livox-SDK2_archive.sha256"

ln -sfn "$BASE/source/b0_vanilla" "$BASE/workspaces/b0/src/fast_lio"
ln -sfn "$DRIVER" "$BASE/workspaces/b0/src/livox_ros_driver2"
printf '%s\n' \
  "fast_lio -> $BASE/source/b0_vanilla" \
  "livox_ros_driver2 -> $DRIVER" \
  >"$BASE/workspaces/b0/source_layout.txt"

sha256sum /usr/local/lib/liblivox_lidar_sdk_shared.so >"$BASE/source/system_livox_sdk_shared.sha256"
ldconfig -p | grep livox >"$BASE/source/system_livox_libraries.txt" || true

echo "Frozen dependency sources and created B0 workspace layout"
