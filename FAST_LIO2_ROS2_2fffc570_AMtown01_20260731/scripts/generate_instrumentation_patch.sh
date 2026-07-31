#!/usr/bin/env bash
set -euo pipefail

WORK=/workspace/baseline_artifacts/b1_work
OUTPUT=/workspace/baseline_artifacts/instrumentation.patch
cp "$WORK/src/laserMapping.cpp" "$WORK/new/src/laserMapping.cpp"
set +e
git diff --no-index --binary "$WORK/old" "$WORK/new" \
  | sed -e 's#a/.*b1_work/old/#a/#' -e 's#b/.*b1_work/new/#b/#' >"$OUTPUT"
diff_rc=${PIPESTATUS[0]}
set -e
test "$diff_rc" = "1"
test -s "$OUTPUT"
git -C /data/fastlio_baseline/source/b0_vanilla apply --check "$OUTPUT"
echo "Generated valid instrumentation.patch"
