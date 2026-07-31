#!/usr/bin/env python3
"""Export nav_msgs/Odometry from a rosbag2 bag to CSV and TUM with validation."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import rosbag2_py
from nav_msgs.msg import Odometry
from rclpy.serialization import deserialize_message


def stamp_sec(msg: Odometry) -> float:
    return msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bag", type=Path)
    parser.add_argument("--topic", default="/Odometry")
    parser.add_argument("--output-prefix", required=True, type=Path)
    args = parser.parse_args()
    args.output_prefix.parent.mkdir(parents=True, exist_ok=True)

    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=str(args.bag), storage_id="mcap"),
        rosbag2_py.ConverterOptions(input_serialization_format="cdr", output_serialization_format="cdr"),
    )
    rows = []
    path_length = 0.0
    previous_position = None
    while reader.has_next():
        topic, data, _ = reader.read_next()
        if topic != args.topic:
            continue
        msg = deserialize_message(data, Odometry)
        p, q = msg.pose.pose.position, msg.pose.pose.orientation
        row = [stamp_sec(msg), p.x, p.y, p.z, q.x, q.y, q.z, q.w]
        rows.append(row)
        if previous_position is not None:
            path_length += math.dist(previous_position, row[1:4])
        previous_position = row[1:4]

    finite = all(math.isfinite(value) for row in rows for value in row)
    monotonic = all(b[0] > a[0] for a, b in zip(rows, rows[1:]))
    norms = [math.sqrt(sum(value * value for value in row[4:8])) for row in rows]
    summary = {
        "topic": args.topic,
        "message_count": len(rows),
        "timestamps_strictly_increasing": monotonic,
        "all_values_finite": finite,
        "quaternion_norm_min": min(norms) if norms else None,
        "quaternion_norm_max": max(norms) if norms else None,
        "path_length_m": path_length,
        "start_stamp": rows[0][0] if rows else None,
        "end_stamp": rows[-1][0] if rows else None,
    }
    with args.output_prefix.with_suffix(".csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["timestamp", "x", "y", "z", "qx", "qy", "qz", "qw"])
        writer.writerows(rows)
    with args.output_prefix.with_suffix(".tum").open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(" ".join(f"{value:.9f}" for value in row) + "\n")
    args.output_prefix.with_name(args.output_prefix.name + "_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    if not rows or not finite or not monotonic or min(norms) < 0.999 or max(norms) > 1.001:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
