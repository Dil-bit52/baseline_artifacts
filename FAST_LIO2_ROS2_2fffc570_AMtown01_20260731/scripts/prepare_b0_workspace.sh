#!/usr/bin/env bash
set -euo pipefail

BASE=/data/fastlio_baseline
DRIVER_SOURCE="$BASE/source/livox_ros_driver2"
DRIVER_BUILD_COPY="$BASE/workspaces/b0/src/livox_ros_driver2"
EXPECTED_LINK="$DRIVER_SOURCE"

if [[ -L "$DRIVER_BUILD_COPY" ]]; then
  test "$(readlink "$DRIVER_BUILD_COPY")" = "$EXPECTED_LINK"
  unlink "$DRIVER_BUILD_COPY"
fi

if [[ ! -e "$DRIVER_BUILD_COPY" ]]; then
  git clone --no-hardlinks "$DRIVER_SOURCE" "$DRIVER_BUILD_COPY"
  git -C "$DRIVER_BUILD_COPY" checkout --detach 13eb05e4e6dd7a765b934d0c5fd6236676a57b49
fi

cp "$DRIVER_BUILD_COPY/package_ROS2.xml" "$DRIVER_BUILD_COPY/package.xml"
if [[ ! -d "$DRIVER_BUILD_COPY/launch" ]]; then
  cp -a "$DRIVER_BUILD_COPY/launch_ROS2" "$DRIVER_BUILD_COPY/launch"
fi

{
  echo "method=independent_local_clone_plus_official_ros2_generated_files"
  echo "source=$DRIVER_SOURCE"
  echo "commit=$(git -C "$DRIVER_BUILD_COPY" rev-parse HEAD)"
  echo "generated_package_xml_from=package_ROS2.xml"
  echo "generated_launch_from=launch_ROS2"
  sha256sum "$DRIVER_BUILD_COPY/package_ROS2.xml" "$DRIVER_BUILD_COPY/package.xml"
} >"$BASE/workspaces/b0/driver_build_prep.txt"

printf '%s\n' \
  "fast_lio -> $BASE/source/b0_vanilla (symbolic link)" \
  "livox_ros_driver2 -> independent clone of $DRIVER_SOURCE with official ROS2 generated files" \
  >"$BASE/workspaces/b0/source_layout.txt"

echo "Prepared livox_ros_driver2 ROS2 build copy without modifying frozen source"
