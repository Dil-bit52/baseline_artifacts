#!/usr/bin/env bash
set -euo pipefail

BASE=/data/fastlio_baseline
ARCHIVE=/workspace/baseline_artifacts
PRIVATE="$ARCHIVE/private/container_preflight"
PUBLIC="$ARCHIVE/public_redacted/container_preflight"
SOURCE_STATE="$ARCHIVE/private/source_state"
FASTLIO=/workspace/src/0_third_party/FAST_LIO_ROS2

mkdir -p \
  "$BASE"/{source,workspaces,datasets,configs,runs,scripts,analysis/csv,analysis/plots,report,manifest} \
  "$BASE"/configs/{original,smoke,performance,map_export,visualization} \
  "$PRIVATE" "$PUBLIC" "$SOURCE_STATE"

{
  date -u +%FT%TZ
  uname -a
  cat /etc/os-release
  lscpu
  free -h
  df -h
  nproc
  gcc --version
  g++ --version
  cmake --version
  python3 --version
  set +u
  source /opt/ros/humble/setup.bash
  set -u
  printf 'ROS_DISTRO=%s\nROS_VERSION=%s\nRMW_IMPLEMENTATION=%s\n' \
    "${ROS_DISTRO:-}" "${ROS_VERSION:-}" "${RMW_IMPLEMENTATION:-}"
  (colcon version-check 2>/dev/null || true)
  ros2 doctor --report || true
} >"$PRIVATE/environment_full.txt" 2>&1

{
  set +u
  source /opt/ros/humble/setup.bash
  set -u
  pkg-config --modversion pcl_common 2>/dev/null || true
  dpkg-query -W | grep -E 'eigen|pcl|openmp|ros-humble' || true
} >"$PRIVATE/critical_packages.txt" 2>&1

ldconfig -p | grep -E 'livox|pcl' >"$PRIVATE/critical_libraries.txt" 2>&1 || true
bash -lc 'source /opt/ros/humble/setup.bash; ros2 pkg list | grep -E "fast_lio|livox" || true' \
  >"$PRIVATE/critical_ros_packages.txt" 2>&1

git -C "$FASTLIO" remote -v >"$SOURCE_STATE/fast_lio_remotes.txt"
git -C "$FASTLIO" branch --show-current >"$SOURCE_STATE/fast_lio_branch.txt"
git -C "$FASTLIO" rev-parse HEAD >"$SOURCE_STATE/fast_lio_head.txt"
git -C "$FASTLIO" log -1 --decorate --stat >"$SOURCE_STATE/fast_lio_log1.txt"
git -C "$FASTLIO" status --porcelain=v2 >"$SOURCE_STATE/fast_lio_status_porcelain_v2.txt"
git -C "$FASTLIO" diff --binary >"$SOURCE_STATE/fast_lio_worktree.patch"
git -C "$FASTLIO" diff --cached --binary >"$SOURCE_STATE/fast_lio_index.patch"
git -C "$FASTLIO" ls-files --others --exclude-standard >"$SOURCE_STATE/fast_lio_untracked.txt"
git -C "$FASTLIO" submodule status --recursive >"$SOURCE_STATE/fast_lio_submodules.txt" || true

python3 "$ARCHIVE/scripts/redact_sensitive.py" \
  "$PRIVATE/environment_full.txt" "$PUBLIC/environment.txt"
cp "$PRIVATE/critical_packages.txt" "$PUBLIC/critical_packages.txt"
cp "$PRIVATE/critical_libraries.txt" "$PUBLIC/critical_libraries.txt"
cp "$PRIVATE/critical_ros_packages.txt" "$PUBLIC/critical_ros_packages.txt"

echo "Container preflight complete: $BASE"
