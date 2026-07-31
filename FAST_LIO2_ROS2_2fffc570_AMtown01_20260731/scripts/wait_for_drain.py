#!/usr/bin/env python3
"""Wait until Odometry is quiet and close to the final LiDAR/bag clock stamp."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import time


def last_row(path: Path):
    try:
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        return rows[-1] if rows else None
    except (FileNotFoundError, PermissionError):
        return None


def number(value):
    if value in (None, "", "None"):
        return None
    return float(value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--latency-csv", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--quiet", type=float, default=3.0)
    parser.add_argument("--max-lag", type=float, default=0.5)
    parser.add_argument("--target-odom-stamp", type=float)
    args = parser.parse_args()

    start = time.monotonic()
    last_count = None
    count_changed_at = start
    final = None
    success = False
    reason = "timeout"
    while time.monotonic() - start < args.timeout:
        row = last_row(args.latency_csv)
        if row:
            count = int(row["odom_message_count"])
            if count != last_count:
                last_count = count
                count_changed_at = time.monotonic()
            backlog = number(row.get("sensor_backlog_sec"))
            clock_lag = number(row.get("clock_lag_sec"))
            quiet = time.monotonic() - count_changed_at
            final = row
            if args.target_odom_stamp is not None:
                latest_odom = number(row.get("latest_odom_stamp"))
                close = count > 0 and latest_odom is not None and latest_odom >= args.target_odom_stamp
            else:
                close = (
                    count > 0
                    and backlog is not None and backlog <= args.max_lag
                    and clock_lag is not None and clock_lag <= args.max_lag
                )
            if quiet >= args.quiet and close:
                success = True
                reason = (
                    "quiet_and_reached_documented_last_usable_scan"
                    if args.target_odom_stamp is not None
                    else "quiet_and_caught_up"
                )
                break
        time.sleep(0.5)

    result = {
        "success": success,
        "reason": reason,
        "drain_time_sec": time.monotonic() - start,
        "final_latency_row": final,
        "target_odom_stamp": args.target_odom_stamp,
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return 0 if success else 2


if __name__ == "__main__":
    raise SystemExit(main())
