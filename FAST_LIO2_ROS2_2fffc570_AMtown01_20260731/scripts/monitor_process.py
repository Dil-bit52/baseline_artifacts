#!/usr/bin/env python3
"""Low-overhead Linux /proc monitor for one verified process."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
from pathlib import Path
import signal
import time


running = True


def stop(_signum, _frame):
    global running
    running = False


def read_status(pid: int) -> dict[str, str]:
    result = {}
    with open(f"/proc/{pid}/status", encoding="utf-8") as stream:
        for line in stream:
            if ":" in line:
                key, value = line.split(":", 1)
                result[key] = value.strip()
    return result


def kb(status: dict[str, str], key: str) -> float:
    value = status.get(key, "0 kB").split()[0]
    return float(value) / 1024.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--interval", type=float, default=0.5)
    args = parser.parse_args()

    expected = os.path.realpath(f"/proc/{args.pid}/exe")
    if not expected.endswith("/fastlio_mapping"):
        raise SystemExit(f"PID {args.pid} executable is not fastlio_mapping: {expected}")

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    ticks = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
    cores = max(1, len(os.sched_getaffinity(0)))
    start = time.monotonic()
    previous_time = start
    previous_ticks = None
    previous_read = previous_write = 0

    fields = [
        "timestamp_utc", "timestamp_monotonic", "elapsed_sec", "pid",
        "cpu_percent_raw", "cpu_percent_normalized", "rss_mb", "vms_mb",
        "shared_mb", "num_threads", "read_bytes_delta", "write_bytes_delta",
        "process_status",
    ]
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        while running and Path(f"/proc/{args.pid}").exists():
            try:
                now = time.monotonic()
                stat = Path(f"/proc/{args.pid}/stat").read_text().split()
                status = read_status(args.pid)
                io_values = {}
                with open(f"/proc/{args.pid}/io", encoding="utf-8") as io_stream:
                    for line in io_stream:
                        key, value = line.split(":", 1)
                        io_values[key] = int(value.strip())
                total_ticks = int(stat[13]) + int(stat[14])
                read_bytes = io_values.get("read_bytes", 0)
                write_bytes = io_values.get("write_bytes", 0)
                if previous_ticks is None:
                    cpu_raw = 0.0
                    read_delta = write_delta = 0
                else:
                    cpu_raw = 100.0 * (total_ticks - previous_ticks) / ticks / max(now - previous_time, 1e-9)
                    read_delta = max(0, read_bytes - previous_read)
                    write_delta = max(0, write_bytes - previous_write)
                writer.writerow({
                    "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "timestamp_monotonic": f"{now:.9f}",
                    "elapsed_sec": f"{now - start:.6f}",
                    "pid": args.pid,
                    "cpu_percent_raw": f"{cpu_raw:.3f}",
                    "cpu_percent_normalized": f"{cpu_raw / cores:.3f}",
                    "rss_mb": f"{kb(status, 'VmRSS'):.3f}",
                    "vms_mb": f"{kb(status, 'VmSize'):.3f}",
                    "shared_mb": f"{kb(status, 'RssFile') + kb(status, 'RssShmem'):.3f}",
                    "num_threads": status.get("Threads", "0"),
                    "read_bytes_delta": read_delta,
                    "write_bytes_delta": write_delta,
                    "process_status": status.get("State", "unknown"),
                })
                stream.flush()
                previous_time, previous_ticks = now, total_ticks
                previous_read, previous_write = read_bytes, write_bytes
            except (FileNotFoundError, ProcessLookupError):
                break
            time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
