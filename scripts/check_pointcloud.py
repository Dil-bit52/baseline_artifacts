#!/usr/bin/env python3
"""Inspect a few Livox CustomMsg and IMU messages without dumping point data."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Imu
from livox_ros_driver2.msg import CustomMsg


def stamp_seconds(stamp) -> float:
    return float(stamp.sec) + float(stamp.nanosec) * 1e-9


class Inspector(Node):
    def __init__(self, lidar_topic: str, imu_topic: str, samples: int, timeout: float):
        super().__init__("fastlio_dataset_compatibility_inspector")
        self.samples = samples
        self.deadline = time.monotonic() + timeout
        self.success = False
        self.finished = False
        self.lidar_rows = []
        self.imu_stamps = []
        self.create_subscription(CustomMsg, lidar_topic, self.on_lidar, 20)
        self.create_subscription(Imu, imu_topic, self.on_imu, 20)
        self.create_timer(0.1, self.check_done)

    def on_lidar(self, msg: CustomMsg) -> None:
        if len(self.lidar_rows) >= self.samples:
            return
        offsets = [int(p.offset_time) for p in msg.points]
        stamp = stamp_seconds(msg.header.stamp)
        previous = self.lidar_rows[-1]["header_stamp_sec"] if self.lidar_rows else None
        self.lidar_rows.append({
            "message_type": "livox_ros_driver2/msg/CustomMsg",
            "header_stamp_sec": stamp,
            "frame_id": msg.header.frame_id,
            "point_num_declared": int(msg.point_num),
            "point_count": len(msg.points),
            "fields": ["offset_time", "x", "y", "z", "reflectivity", "tag", "line"],
            "has_offset_time": bool(offsets),
            "offset_time_min": min(offsets) if offsets else None,
            "offset_time_max": max(offsets) if offsets else None,
            "stamp_delta_sec": None if previous is None else stamp - previous,
        })

    def on_imu(self, msg: Imu) -> None:
        if len(self.imu_stamps) < self.samples:
            self.imu_stamps.append(stamp_seconds(msg.header.stamp))

    def check_done(self) -> None:
        if self.finished:
            return
        enough = len(self.lidar_rows) >= self.samples and len(self.imu_stamps) >= self.samples
        if enough or time.monotonic() >= self.deadline:
            self.finished = True
            self.success = enough
            summary = {
                "lidar_samples": self.lidar_rows,
                "imu_stamps_sec": self.imu_stamps,
                "lidar_stamp_monotonic": all(
                    b["header_stamp_sec"] > a["header_stamp_sec"]
                    for a, b in zip(self.lidar_rows, self.lidar_rows[1:])
                ),
                "imu_stamp_monotonic": all(b > a for a, b in zip(self.imu_stamps, self.imu_stamps[1:])),
                "time_ranges_overlap": bool(self.lidar_rows and self.imu_stamps) and not (
                    self.lidar_rows[-1]["header_stamp_sec"] < self.imu_stamps[0]
                    or self.imu_stamps[-1] < self.lidar_rows[0]["header_stamp_sec"]
                ),
                "finite_stamps": all(math.isfinite(row["header_stamp_sec"]) for row in self.lidar_rows)
                and all(math.isfinite(value) for value in self.imu_stamps),
            }
            print(json.dumps(summary, indent=2, sort_keys=True))
            if not enough:
                self.get_logger().error("Timed out before collecting requested samples")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lidar-topic", default="/livox/lidar")
    parser.add_argument("--imu-topic", default="/livox/imu")
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=25.0)
    args = parser.parse_args()
    rclpy.init()
    node = Inspector(args.lidar_topic, args.imu_topic, args.samples, args.timeout)
    try:
        while rclpy.ok() and not node.finished:
            rclpy.spin_once(node, timeout_sec=0.2)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0 if node.success else 2


if __name__ == "__main__":
    sys.exit(main())
