#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path


BASELINE_ID = "FAST_LIO2_ROS2_2fffc570_AMtown01_20260731"
ROOT = Path("/workspace/baseline_artifacts") / BASELINE_ID


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    checks: dict[str, object] = {}
    manifest = json.loads((ROOT / "manifest/baseline_manifest.json").read_text(encoding="utf-8"))
    checks["baseline_id_matches"] = manifest["baseline_id"] == BASELINE_ID

    hash_failures = []
    hash_lines = (ROOT / "manifest/essential_artifacts_sha256.txt").read_text(encoding="utf-8").splitlines()
    for line in hash_lines:
        expected, relative = line.split("  ", 1)
        path = ROOT / relative
        if not path.is_file() or sha256(path) != expected:
            hash_failures.append(relative)
    checks["essential_hash_count"] = len(hash_lines)
    checks["essential_hash_failures"] = hash_failures

    bundle_failures = []
    for path in sorted((ROOT / "source").glob("*.bundle")):
        result = subprocess.run(["git", "bundle", "verify", str(path)], capture_output=True, text=True)
        if result.returncode != 0:
            bundle_failures.append({"path": path.name, "stderr": result.stderr})
    checks["git_bundle_count"] = len(list((ROOT / "source").glob("*.bundle")))
    checks["git_bundle_failures"] = bundle_failures

    formal_failures = []
    for run_id in ["performance_01", "performance_02", "performance_03"]:
        run = ROOT / "runs" / run_id
        exit_codes = {}
        for line in (run / "exit_codes.txt").read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                exit_codes[key] = value
        required = ["bag_play", "bag_record", "latency_monitor", "process_monitor", "launch", "drain"]
        if any(exit_codes.get(key) != "0" for key in required):
            formal_failures.append({"run_id": run_id, "exit_codes": exit_codes})
        for csv_name in ["frame_metrics.csv", "process_metrics.csv", "ros_latency.csv", "estimated.csv"]:
            with (run / csv_name).open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    for value in row.values():
                        if isinstance(value, str) and value.strip().lower() in {"nan", "inf", "+inf", "-inf"}:
                            formal_failures.append({"run_id": run_id, "file": csv_name, "nonfinite": value})
                            break
    checks["formal_run_failures"] = formal_failures

    privacy_failures = []
    sensitive_patterns = [
        re.compile(r"C:\\Users\\", re.I),
        re.compile(r"D:\\Desktop\\", re.I),
        re.compile(r"(?:TOKEN|PASSWORD|SECRET|COOKIE|API[_-]?KEY)\s*[:=]\s*[^\s,}\]]+", re.I),
    ]
    for directory in [ROOT / "public_redacted", ROOT / "report", ROOT / "manifest"]:
        for path in directory.rglob("*"):
            if not path.is_file() or path.suffix.lower() in {".png", ".pdf", ".xlsx"}:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for pattern in sensitive_patterns:
                if pattern.search(text):
                    privacy_failures.append({"path": path.relative_to(ROOT).as_posix(), "pattern": pattern.pattern})
    checks["public_privacy_failures"] = privacy_failures

    checks["png_count"] = len(list((ROOT / "analysis/plots").glob("*.png")))
    checks["pdf_count"] = len(list((ROOT / "analysis/plots").glob("*.pdf")))
    checks["xlsx_exists"] = (ROOT / "analysis/FAST_LIO2_baseline_results.xlsx").is_file()
    checks["report_exists"] = (ROOT / "report/FAST_LIO2_ROS2_baseline_report.md").is_file()
    checks["b0_binary_matches_manifest"] = sha256(ROOT / manifest["binaries"]["b0_path"]) == manifest["binaries"]["b0_sha256"]
    checks["b1_binary_matches_manifest"] = sha256(ROOT / manifest["binaries"]["b1_path"]) == manifest["binaries"]["b1_sha256"]
    checks["b0_map_matches_manifest"] = sha256(ROOT / manifest["maps"]["b0"]["path"]) == manifest["maps"]["b0"]["sha256"]
    checks["b1_map_matches_manifest"] = sha256(ROOT / manifest["maps"]["b1"]["path"]) == manifest["maps"]["b1"]["sha256"]

    success = (
        checks["baseline_id_matches"]
        and not hash_failures
        and checks["git_bundle_count"] == 5
        and not bundle_failures
        and not formal_failures
        and not privacy_failures
        and checks["png_count"] == 12
        and checks["pdf_count"] == 12
        and checks["xlsx_exists"]
        and checks["report_exists"]
        and checks["b0_binary_matches_manifest"]
        and checks["b1_binary_matches_manifest"]
        and checks["b0_map_matches_manifest"]
        and checks["b1_map_matches_manifest"]
    )
    result = {"success": bool(success), "checks": checks}
    output = ROOT / "manifest/archive_verification.json"
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if not success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
