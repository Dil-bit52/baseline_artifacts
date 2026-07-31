#!/usr/bin/env python3
"""Compare two Odometry CSV trajectories by exact nanosecond timestamp."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path


def load(path: Path):
    rows = []
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            values = {key: float(value) for key, value in row.items()}
            values["stamp_ns"] = round(values["timestamp"] * 1e9)
            rows.append(values)
    return rows


def angle_deg(a, b):
    qa = [a[key] for key in ("qx", "qy", "qz", "qw")]
    qb = [b[key] for key in ("qx", "qy", "qz", "qw")]
    na = math.sqrt(sum(v * v for v in qa))
    nb = math.sqrt(sum(v * v for v in qb))
    dot = abs(sum(x * y for x, y in zip(qa, qb)) / (na * nb))
    return math.degrees(2.0 * math.acos(min(1.0, max(-1.0, dot))))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("b0", type=Path)
    parser.add_argument("b1", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    b0, b1 = load(args.b0), load(args.b1)
    by_stamp_0 = {row["stamp_ns"]: row for row in b0}
    by_stamp_1 = {row["stamp_ns"]: row for row in b1}
    common = sorted(set(by_stamp_0) & set(by_stamp_1))
    differences = []
    for stamp in common:
        a, b = by_stamp_0[stamp], by_stamp_1[stamp]
        position = math.dist([a["x"], a["y"], a["z"]], [b["x"], b["y"], b["z"]])
        differences.append((stamp, position, angle_deg(a, b)))
    final_position = final_rotation = None
    if b0 and b1:
        final_position = math.dist(
            [b0[-1][key] for key in ("x", "y", "z")],
            [b1[-1][key] for key in ("x", "y", "z")],
        )
        final_rotation = angle_deg(b0[-1], b1[-1])
    result = {
        "b0_message_count": len(b0),
        "b1_message_count": len(b1),
        "message_count_difference": len(b1) - len(b0),
        "common_timestamp_count": len(common),
        "b0_unmatched_timestamps": len(set(by_stamp_0) - set(by_stamp_1)),
        "b1_unmatched_timestamps": len(set(by_stamp_1) - set(by_stamp_0)),
        "max_position_difference_m": max((item[1] for item in differences), default=None),
        "max_rotation_difference_deg": max((item[2] for item in differences), default=None),
        "final_position_difference_m": final_position,
        "final_rotation_difference_deg": final_rotation,
    }
    result["equivalent"] = bool(differences) and (
        result["message_count_difference"] == 0
        and result["b0_unmatched_timestamps"] == 0
        and result["b1_unmatched_timestamps"] == 0
        and result["max_position_difference_m"] <= 0.001
        and result["max_rotation_difference_deg"] <= 0.01
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    with args.output.with_suffix(".csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["stamp_ns", "position_difference_m", "rotation_difference_deg"])
        writer.writerows(differences)
    return 0 if result["equivalent"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
