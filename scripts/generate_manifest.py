#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


BASELINE_ID = "FAST_LIO2_ROS2_2fffc570_AMtown01_20260731"
ROOT = Path("/workspace/baseline_artifacts") / BASELINE_ID
MANIFEST_DIR = ROOT / "manifest"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def config_hashes() -> dict[str, str]:
    return {path.name: sha256(path) for path in sorted((ROOT / "configs").glob("*.yaml"))}


def run_exit_codes(run_id: str) -> dict[str, str]:
    path = ROOT / "runs" / run_id / "exit_codes.txt"
    if not path.exists():
        return {}
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


def essential_files() -> list[Path]:
    files: set[Path] = set()
    direct = [ROOT / "instrumentation.patch", ROOT / "TASK_STATUS.md", ROOT / "README.md"]
    files.update(path for path in direct if path.is_file())
    for directory in [
        "analysis/csv", "analysis/plots", "build", "configs", "dataset", "docker_stats",
        "public_redacted", "report", "runs", "scripts", "source",
    ]:
        files.update(path for path in (ROOT / directory).rglob("*") if path.is_file())
    xlsx = ROOT / "analysis/FAST_LIO2_baseline_results.xlsx"
    if xlsx.exists():
        files.add(xlsx)
    return sorted(files, key=lambda path: path.as_posix())


def main() -> None:
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    created = datetime.now(timezone.utc).isoformat()
    runs = ["performance_01", "performance_02", "performance_03"]
    manifest = {
        "baseline_id": BASELINE_ID,
        "created_utc": created,
        "host": "Windows host with Docker Desktop; sensitive host details retained only in private/",
        "container": {
            "id": "dc3ae6023b26be72f110849f9b0edca845434847ed9fd5ef01a77c6a2d6cb8e4",
            "image_id": "sha256:327fe46ebc7cfbc19cdc68a6282169b83a06f0971b53262f63d5484658ad490b",
            "repo_digest": "osrf/ros@sha256:327fe46ebc7cfbc19cdc68a6282169b83a06f0971b53262f63d5484658ad490b",
            "os": "Ubuntu 22.04.5 LTS",
            "cpu_visible": 20,
            "memory_visible": "7.6 GiB",
        },
        "ros": {"distribution": "Humble", "version": 2, "rmw": "rmw_fastrtps_cpp (doctor; env unset)"},
        "compiler": {"gcc": "11.4.0", "cmake": "3.22.1", "python": "3.10.12"},
        "workspaces": {"host_archive": str(ROOT), "linux_high_performance_root": "/data/fastlio_baseline"},
        "source": {
            "repository": "Ericsii/FAST_LIO_ROS2",
            "branch": "ros2",
            "b0_commit": "2fffc570a25d0df172720bac034fbdb6a13d2162",
            "b1_commit": "6d82e211f250a8b97c71eb8112d98e3ec29770ae",
            "ikd_tree_commit": "e2e3f4e9d3b95a9e66b1ba83dc98d4a05ed8a3c4",
            "livox_ros_driver2_commit": "13eb05e4e6dd7a765b934d0c5fd6236676a57b49",
            "livox_sdk2_commit": "22d98dcd4672953fbc96d6bc9f1be7a1c0cfef9e",
            "original_worktrees_modified": True,
            "original_state_preserved_under": "private/source_state",
            "b0_snapshot_clean": True,
            "instrumentation_patch": "instrumentation.patch",
            "instrumentation_patch_sha256": sha256(ROOT / "instrumentation.patch"),
        },
        "binaries": {
            "b0_path": "build/b0/fastlio_mapping",
            "b0_sha256": sha256(ROOT / "build/b0/fastlio_mapping"),
            "b1_path": "build/b1/fastlio_mapping",
            "b1_sha256": sha256(ROOT / "build/b1/fastlio_mapping"),
        },
        "config_sha256": config_hashes(),
        "dataset": {
            "name": "AMtown01_driver2",
            "status": "local derived driver2 conversion of public MARS-LVIG AMtown01; conversion history unavailable",
            "staged_path": "/data/fastlio_baseline/datasets/AMtown01_driver2",
            "duration_sec": 1354.388754976,
            "mcap_bytes": 33009250404,
            "mcap_sha256": "6f3c85f54982d88d1dd2707815922e5a77fa7d64a787a608ac43d6a70f819586",
            "metadata_sha256": "b18d1f4b33e6c16d53f5192da78207930907e4efe4d19b0cd65609bffe40ece0",
            "lidar_messages": 13543,
            "imu_messages": 281894,
            "ground_truth": "N/A: no frozen GT/alignment protocol",
        },
        "commands": {
            "build": "colcon --log-base log build --base-paths src --build-base build --install-base install --packages-up-to fast_lio --event-handlers console_direct+ --cmake-args -DCMAKE_BUILD_TYPE=Release -DCMAKE_EXPORT_COMPILE_COMMANDS=ON -DROS_EDITION=ROS2 -DDISTRO_ROS=humble",
            "launch": "ros2 launch fast_lio mapping.launch.py config_path:=<run_dir> config_file:=config.yaml use_sim_time:=true rviz:=false",
            "play": "ros2 bag play /data/fastlio_baseline/datasets/AMtown01_driver2 --clock --rate 1.0 --delay 5 --topics /livox/lidar /livox/imu",
            "ros_domain_id": 47,
        },
        "formal_runs": [
            {"run_id": run_id, "exit_codes": run_exit_codes(run_id), "result_path": f"runs/{run_id}"}
            for run_id in runs
        ],
        "other_runs": [
            "b0_smoke_01", "b0_full_01", "equivalence_simultaneous_01",
            "equivalence_simultaneous_02", "equivalence_simultaneous_03",
            "warmup_01", "map_export_01", "visualization_01",
        ],
        "equivalence": {
            "accepted_audit": "runs/equivalence_simultaneous_03/equivalence.json",
            "conditions": "same player, 0.1x, delay 5 s, OMP_THREAD_LIMIT=1",
            "max_position_difference_m": 0.0,
            "max_rotation_difference_deg": 0.0,
            "scope_limit": "default multi-thread trials were nondeterministic and are retained",
        },
        "maps": {
            "b0": {"path": "runs/b0_full_01/registered_scan_aggregation.pcd", "points": 8602360, "sha256": "882f2131d9c6235b213653200f4304aaef765da9c9b2c157eaa1f459bc52b9e4"},
            "b1": {"path": "runs/map_export_01/registered_scan_aggregation.pcd", "points": 8590275, "sha256": "b2fe3fdcece1f4291f006e6cdd06dfd70d888907e4531085963126b720859dbe"},
            "semantics": "registered-scan aggregation, not a direct dump of every internal ikd-tree node",
        },
        "reports": {
            "experiment_report": "report/FAST_LIO2_ROS2_baseline_report.md",
            "ppt_page": "report/ppt_page_baseline.md",
            "ppt_tables": ["report/ppt_tables.md", "report/ppt_tables.csv"],
            "analysis_workbook": "analysis/FAST_LIO2_baseline_results.xlsx",
        },
        "essential_hash_list": "manifest/essential_artifacts_sha256.txt",
        "sensitive_data_policy": "private/ is local-only; publish public_redacted/ only",
    }
    json_path = MANIFEST_DIR / "baseline_manifest.json"
    json_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    markdown = f"""# BASELINE MANIFEST

- Baseline ID: `{BASELINE_ID}`
- Created UTC: `{created}`
- B0 commit: `2fffc570a25d0df172720bac034fbdb6a13d2162`
- B1 commit: `6d82e211f250a8b97c71eb8112d98e3ec29770ae`
- B0 binary SHA-256: `{manifest['binaries']['b0_sha256']}`
- B1 binary SHA-256: `{manifest['binaries']['b1_sha256']}`
- Dataset MCAP SHA-256: `{manifest['dataset']['mcap_sha256']}`
- Formal runs: `performance_01`, `performance_02`, `performance_03` (all required exit codes 0)
- Report: `report/FAST_LIO2_ROS2_baseline_report.md`
- Full machine-readable record: `manifest/baseline_manifest.json`
- Essential hashes: `manifest/essential_artifacts_sha256.txt`

The source MCAP remains at `/data/fastlio_baseline/datasets/AMtown01_driver2` and is not duplicated in this archive.  Do not publish `private/`; use `public_redacted/` only.
"""
    (MANIFEST_DIR / "BASELINE_MANIFEST.md").write_text(markdown, encoding="utf-8")

    hash_lines = [f"{sha256(path)}  {path.relative_to(ROOT).as_posix()}" for path in essential_files()]
    (MANIFEST_DIR / "essential_artifacts_sha256.txt").write_text("\n".join(hash_lines) + "\n", encoding="utf-8")
    print(json.dumps({"baseline_id": BASELINE_ID, "essential_file_count": len(hash_lines)}, indent=2))


if __name__ == "__main__":
    main()
