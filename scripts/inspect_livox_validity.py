#!/usr/bin/env python3
"""Count points that satisfy FAST-LIO Avia preprocessor gates without dumping points."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import time

import rclpy
from rclpy.node import Node
from livox_ros_driver2.msg import CustomMsg


class Validity(Node):
    def __init__(self, csv_path: Path, duration: float):
        super().__init__("fastlio_livox_validity_inspector")
        self.deadline = time.monotonic() + duration
        self.finished = False
        self.rows = []
        self.csv_path = csv_path
        self.create_subscription(CustomMsg, "/livox/lidar", self.callback, 20)
        self.create_timer(0.1, self.tick)

    def callback(self, msg):
        gate = 0
        filtered_over_blind = 0
        valid_index = 0
        for point in msg.points[1:]:
            if point.line < 6 and ((point.tag & 0x30) in (0x10, 0x00)):
                gate += 1
                valid_index += 1
                if valid_index % 3 == 0 and point.x * point.x + point.y * point.y + point.z * point.z > 16.0:
                    filtered_over_blind += 1
        self.rows.append({
            "stamp": msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
            "declared_points": int(msg.point_num),
            "tag_line_gate_points": gate,
            "approx_filtered_points_over_4m": filtered_over_blind,
        })

    def tick(self):
        if time.monotonic() >= self.deadline:
            self.finished = True

    def save(self):
        with self.csv_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(self.rows[0].keys()) if self.rows else [
                "stamp", "declared_points", "tag_line_gate_points", "approx_filtered_points_over_4m"
            ])
            writer.writeheader()
            writer.writerows(self.rows)
        counts = [row["approx_filtered_points_over_4m"] for row in self.rows]
        summary = {
            "frames": len(self.rows),
            "first_stamp": self.rows[0]["stamp"] if self.rows else None,
            "last_stamp": self.rows[-1]["stamp"] if self.rows else None,
            "approx_filtered_points_min": min(counts) if counts else None,
            "approx_filtered_points_max": max(counts) if counts else None,
            "frames_with_zero_approx_filtered_points": sum(value == 0 for value in counts),
            "frames_with_fewer_than_5_approx_filtered_points": sum(value < 5 for value in counts),
        }
        self.csv_path.with_name("tail_validity_summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--duration", type=float, default=18.0)
    args = parser.parse_args()
    rclpy.init()
    node = Validity(args.output, args.duration)
    try:
        while rclpy.ok() and not node.finished:
            rclpy.spin_once(node, timeout_sec=0.2)
        node.save()
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0 if node.rows else 2


if __name__ == "__main__":
    raise SystemExit(main())
