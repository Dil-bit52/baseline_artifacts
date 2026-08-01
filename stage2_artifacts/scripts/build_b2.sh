#!/usr/bin/env bash
set -o pipefail

WS=/workspace/stage2_workspaces/b2
ATTEMPT=${1:-build_01}
OUT=/workspace/stage2_artifacts/raw/builds/$ATTEMPT

if [[ -e "$OUT" ]]; then
  echo "Build evidence directory already exists: $OUT" >&2
  exit 2
fi
mkdir -p "$OUT"

set +u
source /opt/ros/humble/setup.bash
set -u
cd "$WS"

git -C src/fast_lio status --porcelain=v2 --branch --ignore-submodules=all >"$OUT/git_status_before.txt"
git -C src/fast_lio rev-parse HEAD >"$OUT/git_head.txt"
git -C src/fast_lio diff --binary --ignore-submodules=all >"$OUT/source_changes.patch"

build_start_ns=$(date +%s%N)
colcon \
  --log-base log \
  build \
  --base-paths src \
  --build-base build \
  --install-base install \
  --packages-up-to fast_lio \
  --event-handlers console_direct+ \
  --cmake-args \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
    -DROS_EDITION=ROS2 \
    -DDISTRO_ROS=humble \
  2>&1 | tee "$OUT/colcon_build.log"
build_rc=${PIPESTATUS[0]}
build_end_ns=$(date +%s%N)

python3 - "$OUT" "$build_start_ns" "$build_end_ns" "$build_rc" <<'PY'
import json
from pathlib import Path
import sys

out = Path(sys.argv[1])
start_ns, end_ns, rc = map(int, sys.argv[2:])
(out / "build_summary.json").write_text(json.dumps({
    "command": "colcon --log-base log build --base-paths src --build-base build --install-base install --packages-up-to fast_lio --event-handlers console_direct+ --cmake-args -DCMAKE_BUILD_TYPE=Release -DCMAKE_EXPORT_COMPILE_COMMANDS=ON -DROS_EDITION=ROS2 -DDISTRO_ROS=humble",
    "elapsed_seconds": (end_ns - start_ns) / 1e9,
    "exit_code": rc,
}, indent=2) + "\n", encoding="utf-8")
PY

printf '%s\n' "$build_rc" >"$OUT/build_exit_code.txt"
if [[ "$build_rc" -ne 0 ]]; then
  exit "$build_rc"
fi

BIN="$WS/install/fast_lio/lib/fast_lio/fastlio_mapping"
test -x "$BIN"
set +u
source "$WS/install/setup.bash"
set -u
ldd "$BIN" >"$OUT/ldd.txt"
if grep -q 'not found' "$OUT/ldd.txt"; then
  echo "Unresolved shared library in B2 binary" >&2
  exit 3
fi
sha256sum "$BIN" >"$OUT/binary_sha256.txt"
grep -E -i 'warning:|error:' "$OUT/colcon_build.log" >"$OUT/warnings_and_errors.txt" || true

echo "B2 build passed: $ATTEMPT"
