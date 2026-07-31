#!/usr/bin/env python3
"""Generate reproducible FAST-LIO2 baseline summaries and figures.

The script intentionally uses every finite raw sample.  It performs no smoothing,
warm-up cropping, outlier removal, or manual correction.
"""

from __future__ import annotations

import csv
import json
import math
from datetime import datetime
from pathlib import Path
from statistics import mean, stdev

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np


DATA_ROOT = Path("/data/fastlio_baseline")
WORKSPACE_ARTIFACTS = Path("/workspace/baseline_artifacts")
OUT = WORKSPACE_ARTIFACTS / "analysis"
CSV_OUT = OUT / "csv"
PLOTS = OUT / "plots"
RUN_IDS = ["performance_01", "performance_02", "performance_03"]
LAST_USABLE_LIDAR_STAMP = 1658138371.9247339

CHINESE_FONT = "/tmp/simhei.ttf"  # local render dependency; not archived
font_manager.fontManager.addfont(CHINESE_FONT)
plt.rcParams["font.family"] = font_manager.FontProperties(fname=CHINESE_FONT).get_name()
plt.rcParams["axes.unicode_minus"] = False


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def floats(rows: list[dict[str, str]], key: str) -> np.ndarray:
    values = []
    for row in rows:
        raw = row.get(key, "")
        if raw not in (None, ""):
            value = float(raw)
            if math.isfinite(value):
                values.append(value)
    return np.asarray(values, dtype=float)


def iso_epoch(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def percentile(values: np.ndarray, q: float) -> float:
    return float(np.percentile(values, q)) if len(values) else math.nan


def regression_per_minute(elapsed: np.ndarray, values: np.ndarray) -> tuple[float, float]:
    if len(elapsed) < 2 or len(values) < 2 or float(np.ptp(elapsed)) == 0.0:
        return math.nan, math.nan
    coefficients = np.polyfit(elapsed, values, 1)
    predicted = np.polyval(coefficients, elapsed)
    residual = float(np.sum((values - predicted) ** 2))
    total = float(np.sum((values - np.mean(values)) ** 2))
    r2 = 1.0 - residual / total if total > 0.0 else math.nan
    return float(coefficients[0] * 60.0), r2


def parse_size_mib(value: str) -> float:
    value = value.strip()
    units = {
        "B": 1.0 / (1024.0 * 1024.0),
        "kB": 1000.0 / (1024.0 * 1024.0),
        "KB": 1000.0 / (1024.0 * 1024.0),
        "KiB": 1.0 / 1024.0,
        "MB": 1_000_000.0 / (1024.0 * 1024.0),
        "MiB": 1.0,
        "GB": 1_000_000_000.0 / (1024.0 * 1024.0),
        "GiB": 1024.0,
    }
    for unit in sorted(units, key=len, reverse=True):
        if value.endswith(unit):
            return float(value[: -len(unit)].strip()) * units[unit]
    return float(value)


def validate_finite_file(path: Path) -> None:
    for row in read_csv(path):
        for raw in row.values():
            if isinstance(raw, str) and raw.strip().lower() in {"nan", "inf", "+inf", "-inf"}:
                raise ValueError(f"non-finite token in {path}: {raw}")


def load_run(run_id: str) -> dict:
    run = DATA_ROOT / "runs" / run_id
    frame = read_csv(run / "frame_metrics.csv")
    process = read_csv(run / "process_metrics.csv")
    latency = read_csv(run / "ros_latency.csv")
    trajectory = read_csv(run / "estimated.csv")
    docker = read_csv(WORKSPACE_ARTIFACTS / "docker_stats" / f"{run_id}.csv")
    summary = json.loads((run / "estimated_summary.json").read_text(encoding="utf-8"))
    drain = json.loads((run / "drain.json").read_text(encoding="utf-8"))
    for name in ["frame_metrics.csv", "process_metrics.csv", "ros_latency.csv", "estimated.csv"]:
        validate_finite_file(run / name)
    return {
        "id": run_id,
        "path": run,
        "frame": frame,
        "process": process,
        "latency": latency,
        "trajectory": trajectory,
        "docker": docker,
        "trajectory_summary": summary,
        "drain": drain,
    }


def summarize(run: dict) -> dict[str, float | int | str | bool]:
    frame = run["frame"]
    process = run["process"]
    latency = run["latency"]
    docker = run["docker"]
    traj = run["trajectory_summary"]

    sensor_t = floats(frame, "timestamp_sensor")
    total = floats(frame, "total_frame_ms")
    rss = floats(process, "rss_mb")
    process_t = floats(process, "elapsed_sec")
    cpu_raw = floats(process, "cpu_percent_raw")
    tree = floats(frame, "kdtree_size_after")
    lidar_buffer = floats(frame, "lidar_buffer_size")
    imu_buffer = floats(frame, "imu_buffer_size")

    frame_wall = np.asarray([iso_epoch(row["timestamp_wall_utc"]) for row in frame], dtype=float)
    proc_wall = np.asarray([iso_epoch(row["timestamp_utc"]) for row in process], dtype=float)
    rss_at_frames = np.interp(frame_wall, proc_wall, rss)
    corr = float(np.corrcoef(tree, rss_at_frames)[0, 1]) if len(tree) > 1 else math.nan

    backlog_raw = floats(latency, "sensor_backlog_sec")
    latency_valid = [
        row
        for row in latency
        if row.get("latest_lidar_stamp")
        and float(row["latest_lidar_stamp"]) <= LAST_USABLE_LIDAR_STAMP + 1e-6
    ]
    backlog_valid = floats(latency_valid, "sensor_backlog_sec")
    clock_lag = floats(latency, "clock_lag_sec")

    docker_cpu = np.asarray(
        [float(row["cpu_percent"].strip().rstrip("%")) for row in docker if row.get("cpu_percent")],
        dtype=float,
    )
    docker_mem = np.asarray(
        [parse_size_mib(row["memory_usage"]) for row in docker if row.get("memory_usage")], dtype=float
    )
    rss_slope, rss_r2 = regression_per_minute(process_t, rss)
    tree_slope, tree_r2 = regression_per_minute(sensor_t - sensor_t[0], tree)

    result: dict[str, float | int | str | bool] = {
        "run_id": run["id"],
        "frame_count": len(frame),
        "trajectory_message_count": int(traj["message_count"]),
        "sensor_duration_sec": float(sensor_t[-1] - sensor_t[0]),
        "trajectory_path_length_m": float(traj["path_length_m"]),
        "trajectory_all_finite": bool(traj["all_values_finite"]),
        "trajectory_timestamps_strict": bool(traj["timestamps_strictly_increasing"]),
        "total_frame_ms_mean": float(np.mean(total)),
        "total_frame_ms_p50": percentile(total, 50),
        "total_frame_ms_p95": percentile(total, 95),
        "total_frame_ms_p99": percentile(total, 99),
        "total_frame_ms_max": float(np.max(total)),
        "rss_mib_initial": float(rss[0]),
        "rss_mib_final": float(rss[-1]),
        "rss_mib_peak": float(np.max(rss)),
        "rss_mib_slope_per_min": rss_slope,
        "rss_linear_regression_r2": rss_r2,
        "process_cpu_percent_mean": float(np.mean(cpu_raw)),
        "process_cpu_percent_peak": float(np.max(cpu_raw)),
        "kdtree_points_initial": int(tree[0]),
        "kdtree_points_final": int(tree[-1]),
        "kdtree_points_peak": int(np.max(tree)),
        "kdtree_points_slope_per_min": tree_slope,
        "kdtree_linear_regression_r2": tree_r2,
        "rss_kdtree_pearson": corr,
        "lidar_buffer_max": int(np.max(lidar_buffer)),
        "imu_buffer_max": int(np.max(imu_buffer)),
        "sensor_backlog_sec_max_raw": float(np.max(backlog_raw)),
        "sensor_backlog_sec_max_valid_window": float(np.max(backlog_valid)),
        "clock_lag_sec_max_raw": float(np.max(clock_lag)),
        "drain_time_sec": float(run["drain"]["drain_time_sec"]),
        "drain_success": bool(run["drain"]["success"]),
        "docker_sample_count": len(docker),
        "docker_cpu_percent_mean": float(np.mean(docker_cpu)),
        "docker_cpu_percent_peak": float(np.max(docker_cpu)),
        "docker_memory_mib_peak": float(np.max(docker_mem)),
    }
    for field in [
        "nearest_search_ms",
        "scan_match_ms",
        "ekf_update_ms",
        "map_insert_ms",
        "map_delete_ms",
        "map_update_ms",
    ]:
        values = floats(frame, field)
        result[f"{field}_mean"] = float(np.mean(values))
        result[f"{field}_p95"] = percentile(values, 95)
        result[f"{field}_p99"] = percentile(values, 99)
    return result


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def make_aggregate(summaries: list[dict]) -> list[dict[str, str | float]]:
    rows: list[dict[str, str | float]] = []
    for key in summaries[0]:
        values = [row[key] for row in summaries]
        if all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values):
            numeric = [float(value) for value in values]
            rows.append(
                {
                    "metric": key,
                    "mean": mean(numeric),
                    "sample_std": stdev(numeric),
                    "min": min(numeric),
                    "max": max(numeric),
                    "n": len(numeric),
                }
            )
    return rows


def style(ax, title: str, xlabel: str, ylabel: str) -> None:
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.25)


def save(fig, name: str) -> None:
    fig.tight_layout()
    png_path = PLOTS / name
    fig.savefig(png_path, dpi=220, bbox_inches="tight")
    fig.savefig(png_path.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)


def generate_figures(runs: list[dict], summaries: list[dict]) -> None:
    colors = ["#1769aa", "#e67e22", "#2e7d32"]

    fig, ax = plt.subplots(figsize=(8, 7))
    for run, color in zip(runs, colors):
        x = floats(run["trajectory"], "x")
        y = floats(run["trajectory"], "y")
        ax.plot(x, y, lw=0.8, color=color, label=run["id"])
    ax.axis("equal")
    ax.legend()
    style(ax, "AMtown01 三次正式运行 XY 估计轨迹（无 GT）", "x（m）", "y（m）")
    save(fig, "01_trajectory_xy.png")

    fig, ax = plt.subplots(figsize=(10, 5))
    for run, color in zip(runs, colors):
        t = floats(run["process"], "elapsed_sec") / 60.0
        ax.plot(t, floats(run["process"], "rss_mb"), lw=0.7, color=color, label=run["id"])
    ax.legend()
    note = "\n".join(
        f"Run {i + 1}: {row['rss_mib_initial']:.1f}→{row['rss_mib_final']:.1f}, "
        f"peak {row['rss_mib_peak']:.1f} MiB, slope {row['rss_mib_slope_per_min']:.2f} MiB/min, "
        f"R2={row['rss_linear_regression_r2']:.3f}"
        for i, row in enumerate(summaries)
    )
    ax.text(0.99, 0.02, note, transform=ax.transAxes, ha="right", va="bottom", fontsize=8,
            bbox=dict(fc="white", alpha=0.8, ec="#999999"))
    style(ax, "AMtown01 FAST-LIO2 进程 RSS 随时间变化（原始样本）", "运行时间（min）", "RSS（MiB）")
    save(fig, "02_rss_over_time.png")

    fig, ax = plt.subplots(figsize=(10, 5))
    for run, color in zip(runs, colors):
        t = floats(run["frame"], "timestamp_sensor")
        t = (t - t[0]) / 60.0
        ax.plot(t, floats(run["frame"], "kdtree_size_after"), lw=0.6, color=color, label=run["id"])
    ax.legend()
    note = "\n".join(
        f"Run {i + 1}: {row['kdtree_points_initial']}→{row['kdtree_points_final']}, "
        f"peak {row['kdtree_points_peak']}, slope {row['kdtree_points_slope_per_min']:.0f} points/min"
        for i, row in enumerate(summaries)
    )
    ax.text(0.99, 0.02, note, transform=ax.transAxes, ha="right", va="bottom", fontsize=8,
            bbox=dict(fc="white", alpha=0.8, ec="#999999"))
    style(ax, "AMtown01 ikd-Tree 地图点数随时间变化（逐帧原始值）", "传感器时间（min）", "地图点数")
    save(fig, "03_kdtree_points_over_time.png")

    fig, ax = plt.subplots(figsize=(8, 6))
    for run, color in zip(runs, colors):
        frame_wall = np.asarray([iso_epoch(r["timestamp_wall_utc"]) for r in run["frame"]])
        proc_wall = np.asarray([iso_epoch(r["timestamp_utc"]) for r in run["process"]])
        rss = np.interp(frame_wall, proc_wall, floats(run["process"], "rss_mb"))
        tree = floats(run["frame"], "kdtree_size_after")
        ax.scatter(tree[::20], rss[::20], s=4, alpha=0.35, color=color, label=run["id"])
    ax.legend(markerscale=3)
    corr_note = "；".join(f"Run {i + 1} r={row['rss_kdtree_pearson']:.3f}" for i, row in enumerate(summaries))
    ax.text(0.02, 0.98, corr_note, transform=ax.transAxes, va="top", fontsize=9,
            bbox=dict(fc="white", alpha=0.8, ec="#999999"))
    style(ax, "AMtown01 RSS 与 ikd-Tree 点数关系（墙钟时间对齐，仅相关性）", "ikd-Tree 点数", "RSS（MiB）")
    save(fig, "04_rss_vs_kdtree_points.png")

    fig, ax = plt.subplots(figsize=(10, 5))
    for run, color in zip(runs, colors):
        t = floats(run["frame"], "timestamp_sensor")
        ax.plot((t - t[0]) / 60.0, floats(run["frame"], "total_frame_ms"), lw=0.45, alpha=0.7, color=color, label=run["id"])
    aggregate_total = np.concatenate([floats(run["frame"], "total_frame_ms") for run in runs])
    for q, ls, color in [(50, ":", "#555555"), (95, "--", "#8e44ad"), (99, "-.", "#c0392b")]:
        value = percentile(aggregate_total, q)
        ax.axhline(value, color=color, ls=ls, lw=1.0, label=f"P{q}={value:.2f} ms")
    ax.axhline(float(np.mean(aggregate_total)), color="#000000", lw=1.0, label=f"mean={np.mean(aggregate_total):.2f} ms")
    ax.axhline(100.0, color="#d35400", lw=1.2, label="10 Hz LiDAR 周期=100 ms")
    ax.legend()
    style(ax, "AMtown01 单帧总处理时间（原始帧，不隐藏异常点）", "传感器时间（min）", "耗时（ms）")
    save(fig, "05_total_frame_time.png")

    run = runs[0]
    fig, ax = plt.subplots(figsize=(10, 5))
    t = floats(run["frame"], "timestamp_sensor")
    t = (t - t[0]) / 60.0
    for field in ["nearest_search_ms", "scan_match_ms", "ekf_update_ms", "map_insert_ms", "map_delete_ms"]:
        ax.plot(t, floats(run["frame"], field), lw=0.45, alpha=0.65, label=field.removesuffix("_ms"))
    ax.legend(ncol=3)
    style(ax, "AMtown01 Run 1 主要模块耗时（原始帧）", "传感器时间（min）", "耗时（ms）")
    save(fig, "06_module_times.png")

    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    for run, color in zip(runs, colors):
        rows = [r for r in run["latency"] if r.get("sensor_backlog_sec")]
        t = floats(rows, "elapsed_sec") / 60.0
        axes[0].plot(t, floats(rows, "sensor_backlog_sec"), lw=0.7, color=color, label=run["id"])
        axes[1].plot(t, floats(rows, "clock_lag_sec"), lw=0.7, color=color, label=run["id"])
    axes[0].axhline(9.7021222, color="black", ls="--", lw=0.8, label="数据尾部无有效点间隔 9.702 s")
    axes[0].legend(ncol=2)
    axes[1].legend(ncol=3)
    style(axes[0], "sensor backlog（含数据尾部无效帧）", "", "时间差（s）")
    style(axes[1], "clock lag 与排空阶段", "监控时间（min）", "时间差（s）")
    fig.suptitle("AMtown01 三次正式运行积压指标（原始样本）")
    save(fig, "07_backlog_and_clock_lag.png")

    labels = [row["run_id"] for row in summaries]
    x = np.arange(len(labels))
    fig, axes = plt.subplots(2, 3, figsize=(14, 8))
    metrics = [
        ("rss_mib_peak", "峰值 RSS（MiB）"),
        ("kdtree_points_final", "结束地图点数"),
        ("total_frame_ms_mean", "平均单帧耗时（ms）"),
        ("total_frame_ms_p95", "P95 单帧耗时（ms）"),
        ("trajectory_path_length_m", "轨迹长度（m；非精度）"),
    ]
    for ax, (key, ylabel) in zip(axes.flat, metrics):
        ax.bar(x, [row[key] for row in summaries], color=colors)
        ax.set_ylabel(ylabel)
    axes.flat[-1].axis("off")
    axes.flat[-1].text(0.05, 0.85, "ATE / RPE = N/A\n无已冻结且有对齐协议的 GT\n三次标准差仅表示本实现重复性",
                       va="top", fontsize=12, bbox=dict(boxstyle="round", fc="#fff3cd", ec="#b7950b"))
    for ax in axes:
        pass
    for ax in axes.flat[:-1]:
        ax.set_xticks(x, [s.replace("performance_", "Run ") for s in labels])
        ax.grid(True, axis="y", alpha=0.25)
    fig.suptitle("AMtown01 三次正式运行对比")
    save(fig, "08_three_run_comparison.png")

    fig, ax = plt.subplots(figsize=(10, 5))
    for run, color in zip(runs, colors):
        t = floats(run["process"], "elapsed_sec") / 60.0
        ax.plot(t, floats(run["process"], "cpu_percent_raw"), lw=0.55, alpha=0.7, color=color, label=run["id"])
    ax.legend()
    style(ax, "AMtown01 FAST-LIO2 进程 CPU（原始样本）", "运行时间（min）", "CPU（%）")
    save(fig, "09_process_cpu_over_time.png")

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.axis("off")
    text = (
        "FAST-LIO2 ROS2 冻结环境与 AMtown01 数据集\n\n"
        "FAST-LIO2：2fffc570a25d0df172720bac034fbdb6a13d2162（ros2）\n"
        "B1：6d82e211f250a8b97c71eb8112d98e3ec29770ae\n"
        "B1 binary SHA-256：d44ba02343650522f112764435d6e5f398456a22254a7363c691a12597adc10d\n"
        "数据：AMtown01 driver2 本地派生副本，1354.389 s；LiDAR 13,543 帧，IMU 281,894 条\n"
        "ROS 2 Humble | Ubuntu 22.04.5 | GCC 11.4 | CMake 3.22.1\n"
        "容器：osrf/ros:humble-desktop；20 CPU；可见内存 7.6 GiB\n"
        "正式协议：全 bag、1.0×，关闭 Path/点云/PCD/RViz"
    )
    ax.text(0.02, 0.95, text, va="top", fontsize=12, linespacing=1.5)
    save(fig, "10_environment_info_card.png")

    fig, ax = plt.subplots(figsize=(13, 4))
    ax.axis("off")
    nodes = [
        (0.06, "LiDAR + IMU\n冻结 MCAP"),
        (0.22, "点云预处理\nIMU 传播/去畸变"),
        (0.40, "Scan-to-Map\nESIKF 更新"),
        (0.58, "ikd-Tree\n增量地图更新"),
        (0.76, "Odometry / TF\n帧级指标"),
        (0.92, "CSV / MCAP\n哈希与分析"),
    ]
    for x0, label in nodes:
        ax.text(x0, 0.5, label, ha="center", va="center", bbox=dict(boxstyle="round,pad=0.6", fc="#eaf2f8", ec="#1769aa"))
    for (x0, _), (x1, _) in zip(nodes, nodes[1:]):
        ax.annotate("", xy=(x1 - 0.06, 0.5), xytext=(x0 + 0.06, 0.5), arrowprops=dict(arrowstyle="->", lw=1.8))
    ax.set_title("FAST-LIO2 基线流程与正式性能测量链路")
    save(fig, "11_measurement_flow.png")


def write_ppt_table(summaries: list[dict], aggregates: list[dict]) -> None:
    selected = {
        row["metric"]: row for row in aggregates
        if row["metric"] in {
            "total_frame_ms_mean", "total_frame_ms_p95", "total_frame_ms_p99",
            "rss_mib_peak", "rss_mib_slope_per_min", "kdtree_points_final",
            "trajectory_path_length_m", "sensor_backlog_sec_max_valid_window",
        }
    }
    lines = [
        "# FAST-LIO2 ROS2 baseline — PPT data tables",
        "",
        "All values below are generated from the three accepted formal runs without smoothing or outlier removal.",
        "",
        "| Metric | 3-run mean | sample std | unit |",
        "|---|---:|---:|---|",
    ]
    units = {
        "total_frame_ms_mean": "ms", "total_frame_ms_p95": "ms", "total_frame_ms_p99": "ms",
        "rss_mib_peak": "MiB", "rss_mib_slope_per_min": "MiB/min",
        "kdtree_points_final": "points", "trajectory_path_length_m": "m",
        "sensor_backlog_sec_max_valid_window": "s",
    }
    for key in units:
        row = selected[key]
        lines.append(f"| {key} | {row['mean']:.6f} | {row['sample_std']:.6f} | {units[key]} |")
    lines += ["", "| Run | frames | path (m) | frame P95 (ms) | peak RSS (MiB) | final tree points |", "|---|---:|---:|---:|---:|---:|"]
    for row in summaries:
        lines.append(
            f"| {row['run_id']} | {row['frame_count']} | {row['trajectory_path_length_m']:.3f} | "
            f"{row['total_frame_ms_p95']:.3f} | {row['rss_mib_peak']:.3f} | {row['kdtree_points_final']} |"
        )
    (OUT / "ppt_data_tables.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    CSV_OUT.mkdir(parents=True, exist_ok=True)
    PLOTS.mkdir(parents=True, exist_ok=True)
    runs = [load_run(run_id) for run_id in RUN_IDS]
    summaries = [summarize(run) for run in runs]
    aggregates = make_aggregate(summaries)
    write_csv(CSV_OUT / "run_summary.csv", summaries)
    write_csv(CSV_OUT / "repeatability_summary.csv", aggregates)
    write_csv(CSV_OUT / "frame_time_summary.csv", [
        {key: row[key] for key in ["run_id", "frame_count", "total_frame_ms_mean", "total_frame_ms_p50", "total_frame_ms_p95", "total_frame_ms_p99", "total_frame_ms_max"]}
        for row in summaries
    ])
    write_csv(CSV_OUT / "map_growth_summary.csv", [
        {key: row[key] for key in ["run_id", "kdtree_points_initial", "kdtree_points_final", "kdtree_points_peak", "kdtree_points_slope_per_min", "kdtree_linear_regression_r2", "rss_kdtree_pearson"]}
        for row in summaries
    ])
    write_csv(CSV_OUT / "latency_summary.csv", [
        {key: row[key] for key in ["run_id", "sensor_backlog_sec_max_raw", "sensor_backlog_sec_max_valid_window", "clock_lag_sec_max_raw", "drain_time_sec", "lidar_buffer_max", "imu_buffer_max"]}
        for row in summaries
    ])
    (CSV_OUT / "run_summary.json").write_text(json.dumps(summaries, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_ppt_table(summaries, aggregates)
    generate_figures(runs, summaries)
    validation = {
        "accepted_run_ids": RUN_IDS,
        "formal_run_count": len(runs),
        "all_frame_counts_13334": all(row["frame_count"] == 13334 for row in summaries),
        "all_trajectories_finite": all(row["trajectory_all_finite"] for row in summaries),
        "all_trajectory_timestamps_strict": all(row["trajectory_timestamps_strict"] for row in summaries),
        "png_figure_count": len(list(PLOTS.glob("*.png"))),
        "pdf_figure_count": len(list(PLOTS.glob("*.pdf"))),
        "png_dpi": 220,
        "smoothing_applied": False,
        "outliers_removed": False,
    }
    (CSV_OUT / "analysis_validation.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(validation, indent=2))


if __name__ == "__main__":
    main()
