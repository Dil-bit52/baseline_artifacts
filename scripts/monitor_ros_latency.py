#!/usr/bin/env python3
"""Record sensor backlog and bag-clock lag; these are not end-to-end latency."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
from pathlib import Path
import signal
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from nav_msgs.msg import Odometry
from rosgraph_msgs.msg import Clock
from livox_ros_driver2.msg import CustomMsg


def sec(stamp) -> float:
    return float(stamp.sec) + float(stamp.nanosec) * 1e-9


class LatencyMonitor(Node):
    def __init__(self, output: Path, interval: float):
        super().__init__("fastlio_latency_monitor")
        qos = QoSProfile(depth=20, reliability=ReliabilityPolicy.BEST_EFFORT, durability=DurabilityPolicy.VOLATILE)
        self.latest_lidar = self.latest_odom = self.latest_clock = None
        self.lidar_count = self.odom_count = 0
        self.stream = output.open("w", newline="", encoding="utf-8")
        self.writer = csv.DictWriter(self.stream, fieldnames=[
            "timestamp_utc", "timestamp_monotonic", "elapsed_sec",
            "latest_lidar_stamp", "latest_odom_stamp", "latest_clock_stamp",
            "sensor_backlog_sec", "clock_lag_sec", "odom_message_count", "lidar_message_count",
        ])
        self.writer.writeheader()
        self.start = time.monotonic()
        self.create_subscription(CustomMsg, "/livox/lidar", self.lidar, qos)
        self.create_subscription(Odometry, "/Odometry", self.odom, qos)
        self.create_subscription(Clock, "/clock", self.clock, qos)
        self.create_timer(interval, self.sample)

    def lidar(self, msg):
        self.latest_lidar = sec(msg.header.stamp)
        self.lidar_count += 1

    def odom(self, msg):
        self.latest_odom = sec(msg.header.stamp)
        self.odom_count += 1

    def clock(self, msg):
        self.latest_clock = sec(msg.clock)

    def sample(self):
        now = time.monotonic()
        backlog = None if self.latest_lidar is None or self.latest_odom is None else self.latest_lidar - self.latest_odom
        lag = None if self.latest_clock is None or self.latest_odom is None else self.latest_clock - self.latest_odom
        self.writer.writerow({
            "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "timestamp_monotonic": f"{now:.9f}",
            "elapsed_sec": f"{now - self.start:.6f}",
            "latest_lidar_stamp": self.latest_lidar,
            "latest_odom_stamp": self.latest_odom,
            "latest_clock_stamp": self.latest_clock,
            "sensor_backlog_sec": backlog,
            "clock_lag_sec": lag,
            "odom_message_count": self.odom_count,
            "lidar_message_count": self.lidar_count,
        })
        self.stream.flush()

    def close(self):
        self.sample()
        self.stream.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--interval", type=float, default=0.5)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rclpy.init()
    node = LatencyMonitor(args.output, args.interval)
    stopping = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        while rclpy.ok() and not stopping:
            rclpy.spin_once(node, timeout_sec=0.2)
    finally:
        node.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
