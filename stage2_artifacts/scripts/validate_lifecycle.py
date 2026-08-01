#!/usr/bin/env python3
import argparse
import csv
import json
import math
from pathlib import Path


FRAME_COLUMNS = [
    "timestamp", "frame_index", "input_points", "observed_voxels", "new_voxels",
    "reobserved_voxels", "total_tracked_voxels", "elapsed_ms",
]
VOXEL_COLUMNS = [
    "voxel_x", "voxel_y", "voxel_z", "center_x", "center_y", "center_z",
    "first_seen_time", "last_seen_time", "lifespan_sec", "total_point_hits",
    "observed_frames", "active_time_bins",
]


def finite(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"non-finite value: {value}")
    return number


def validate_enabled(run: Path) -> dict:
    lifecycle = run / "lifecycle"
    frame_path = lifecycle / "frame_lifecycle.csv"
    voxel_path = lifecycle / "voxel_lifecycle_final.csv"
    summary_path = lifecycle / "lifecycle_run_summary.json"
    checkpoint_path = lifecycle / "voxel_lifecycle_checkpoints.csv"
    for path in (frame_path, voxel_path, summary_path, checkpoint_path):
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"missing or empty required output: {path}")

    frame_rows = 0
    previous_timestamp = -math.inf
    previous_total = 0
    frame_input_sum = 0
    elapsed_values = []
    with frame_path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != FRAME_COLUMNS:
            raise ValueError(f"unexpected frame columns: {reader.fieldnames}")
        for row in reader:
            frame_rows += 1
            timestamp = finite(row["timestamp"])
            elapsed_ms = finite(row["elapsed_ms"])
            frame_index = int(row["frame_index"])
            input_points = int(row["input_points"])
            observed = int(row["observed_voxels"])
            new = int(row["new_voxels"])
            reobserved = int(row["reobserved_voxels"])
            total = int(row["total_tracked_voxels"])
            if frame_index != frame_rows:
                raise ValueError(f"non-contiguous frame index at row {frame_rows}")
            if timestamp <= previous_timestamp:
                raise ValueError(f"timestamps are not strictly increasing at frame {frame_index}")
            if observed != new + reobserved:
                raise ValueError(f"new + reobserved mismatch at frame {frame_index}")
            if total != previous_total + new:
                raise ValueError(f"tracked voxel accumulation mismatch at frame {frame_index}")
            if input_points < observed or elapsed_ms < 0.0:
                raise ValueError(f"invalid point/time counts at frame {frame_index}")
            previous_timestamp = timestamp
            previous_total = total
            frame_input_sum += input_points
            elapsed_values.append(elapsed_ms)
    if frame_rows == 0:
        raise ValueError("frame_lifecycle.csv has no data rows")

    voxel_rows = 0
    voxel_hit_sum = 0
    with voxel_path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or any(column not in reader.fieldnames for column in VOXEL_COLUMNS):
            raise ValueError(f"missing voxel columns: {reader.fieldnames}")
        for row in reader:
            voxel_rows += 1
            for column in ("center_x", "center_y", "center_z", "mean_x", "mean_y", "mean_z",
                           "first_seen_time", "last_seen_time", "lifespan_sec"):
                finite(row[column])
            first_seen = float(row["first_seen_time"])
            last_seen = float(row["last_seen_time"])
            lifespan = float(row["lifespan_sec"])
            hits = int(row["total_point_hits"])
            frames = int(row["observed_frames"])
            bins = int(row["active_time_bins"])
            if first_seen > last_seen or lifespan < -1e-9:
                raise ValueError(f"invalid lifecycle ordering at voxel row {voxel_rows}")
            if frames < bins or hits < frames or bins < 1:
                raise ValueError(f"invalid observation counts at voxel row {voxel_rows}")
            voxel_hit_sum += hits
    if voxel_rows == 0:
        raise ValueError("voxel_lifecycle_final.csv has no data rows")

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary["frames"] != frame_rows:
        raise ValueError("summary frame count mismatch")
    if summary["total_tracked_voxels"] != voxel_rows or previous_total != voxel_rows:
        raise ValueError("summary/final voxel count mismatch")
    if summary["total_input_points"] != frame_input_sum:
        raise ValueError("summary input point count mismatch")
    if summary["total_finite_points"] != voxel_hit_sum:
        raise ValueError("finite point/hit total mismatch")
    if summary["invalid_timestamp_frames"] != 0 or summary["non_monotonic_timestamp_frames"] != 0:
        raise ValueError("summary reports invalid or non-monotonic timestamps")

    return {
        "status": "passed",
        "mode": "enabled",
        "frame_rows": frame_rows,
        "voxel_rows": voxel_rows,
        "input_points": frame_input_sum,
        "total_point_hits": voxel_hit_sum,
        "observer_elapsed_ms_mean": sum(elapsed_values) / len(elapsed_values),
        "observer_elapsed_ms_max": max(elapsed_values),
        "checks": [
            "required files and columns", "strictly increasing timestamps",
            "contiguous frame indices", "new/reobserved accounting", "finite numeric fields",
            "first_seen_time <= last_seen_time", "observed_frames >= active_time_bins",
            "nonzero voxel count", "summary/CSV cross-checks",
        ],
    }


def validate_disabled(run: Path) -> dict:
    lifecycle = run / "lifecycle"
    generated = [] if not lifecycle.exists() else [p.name for p in lifecycle.iterdir() if p.is_file()]
    if generated:
        raise ValueError(f"disabled observer generated lifecycle files: {generated}")
    return {
        "status": "passed",
        "mode": "disabled",
        "generated_lifecycle_files": generated,
        "checks": ["observer disabled", "no lifecycle output files generated"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_directory", type=Path)
    parser.add_argument("--disabled", action="store_true")
    args = parser.parse_args()
    result = validate_disabled(args.run_directory) if args.disabled else validate_enabled(args.run_directory)
    output = args.run_directory / "lifecycle_validation.json"
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
