#!/usr/bin/env bash
set -euo pipefail

BASE=/data/fastlio_baseline
ARCHIVE=/workspace/baseline_artifacts
B0="$BASE/source/b0_vanilla"
B1="$BASE/source/b1_instrumented"
WS="$BASE/workspaces/b1"
PATCH="$ARCHIVE/instrumentation.patch"
BASE_COMMIT=2fffc570a25d0df172720bac034fbdb6a13d2162
IKD_COMMIT=e2e3f4e9d3b95a9e66b1ba83dc98d4a05ed8a3c4

test "$(git -C "$B0" rev-parse HEAD)" = "$BASE_COMMIT"
test -z "$(git -C "$B0" status --porcelain=v2)"
git -C "$B0" apply --check "$PATCH"

if [[ ! -e "$B1" ]]; then
  git clone --no-hardlinks "$B0" "$B1"
  git -C "$B1" checkout --detach "$BASE_COMMIT"
  git -C "$B1" config submodule.include/ikd-Tree.url "$B0/include/ikd-Tree"
  git -C "$B1" -c protocol.file.allow=always submodule update --init --recursive
  git -C "$B1" switch -c experiment/baseline-instrumentation
  git -C "$B1" apply "$PATCH"
  git -C "$B1" diff --stat >"$ARCHIVE/instrumentation_diff_stat.txt"
  git -C "$B1" add src/laserMapping.cpp
  git -C "$B1" -c user.name='FAST-LIO Baseline' -c user.email='baseline@local.invalid' \
    commit -m 'chore: add non-invasive FAST-LIO2 baseline instrumentation'
fi

test "$(git -C "$B1" rev-parse HEAD^)" = "$BASE_COMMIT"
test "$(git -C "$B1/include/ikd-Tree" rev-parse HEAD)" = "$IKD_COMMIT"
test -z "$(git -C "$B1" status --porcelain=v2)"
git -C "$B1" rev-parse HEAD >"$BASE/source/b1_commit.txt"
git -C "$B1" log -1 --decorate --stat >"$BASE/source/b1_log1.txt"
git -C "$B1" archive --format=tar HEAD | sha256sum >"$BASE/source/b1_source_archive.sha256"
sha256sum "$PATCH" >"$BASE/source/instrumentation_patch.sha256"

mkdir -p "$WS/src"
if [[ ! -e "$WS/src/fast_lio" ]]; then
  git clone --no-hardlinks "$B1" "$WS/src/fast_lio"
  git -C "$WS/src/fast_lio" config submodule.include/ikd-Tree.url "$B0/include/ikd-Tree"
  git -C "$WS/src/fast_lio" -c protocol.file.allow=always submodule update --init --recursive
fi
if [[ ! -e "$WS/src/livox_ros_driver2" ]]; then
  git clone --no-hardlinks "$BASE/source/livox_ros_driver2" "$WS/src/livox_ros_driver2"
  git -C "$WS/src/livox_ros_driver2" checkout --detach 13eb05e4e6dd7a765b934d0c5fd6236676a57b49
  cp "$WS/src/livox_ros_driver2/package_ROS2.xml" "$WS/src/livox_ros_driver2/package.xml"
  cp -a "$WS/src/livox_ros_driver2/launch_ROS2" "$WS/src/livox_ros_driver2/launch"
fi
printf '%s\n' \
  "fast_lio -> independent runtime clone of $B1" \
  "livox_ros_driver2 -> independent clone with official ROS2 generated files" \
  >"$WS/source_layout.txt"

echo "Frozen committed B1 source and prepared isolated workspace"
