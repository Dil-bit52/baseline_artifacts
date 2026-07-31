#!/usr/bin/env bash
set -euo pipefail

BASE=/data/fastlio_baseline
ORIGINAL=/workspace/src/0_third_party/FAST_LIO_ROS2
ORIGINAL_IKD="$ORIGINAL/include/ikd-Tree"
B0="$BASE/source/b0_vanilla"
EXPECTED_FASTLIO=2fffc570a25d0df172720bac034fbdb6a13d2162
EXPECTED_IKD=e2e3f4e9d3b95a9e66b1ba83dc98d4a05ed8a3c4

test "$(git -C "$ORIGINAL" rev-parse HEAD)" = "$EXPECTED_FASTLIO"
test "$(git -C "$ORIGINAL_IKD" rev-parse HEAD)" = "$EXPECTED_IKD"
if [[ ! -e "$B0" ]]; then
  git clone --no-hardlinks "$ORIGINAL" "$B0"
  git -C "$B0" checkout --detach "$EXPECTED_FASTLIO"
  git -C "$B0" config submodule.include/ikd-Tree.url "$ORIGINAL_IKD"
  git -C "$B0" -c protocol.file.allow=always submodule update --init --recursive
fi

test "$(git -C "$B0" rev-parse HEAD)" = "$EXPECTED_FASTLIO"
test "$(git -C "$B0/include/ikd-Tree" rev-parse HEAD)" = "$EXPECTED_IKD"
test -z "$(git -C "$B0" status --porcelain=v2)"

git -C "$B0" status --porcelain=v2 >"$BASE/source/b0_status_porcelain_v2.txt"
git -C "$B0" rev-parse HEAD >"$BASE/source/b0_commit.txt"
git -C "$B0" submodule status --recursive >"$BASE/source/b0_submodules.txt"
git -C "$B0" archive --format=tar HEAD | sha256sum >"$BASE/source/b0_source_archive.sha256"
git -C "$B0/include/ikd-Tree" archive --format=tar HEAD | sha256sum \
  >"$BASE/source/b0_ikd_tree_archive.sha256"

echo "Frozen clean B0 source at $B0"
