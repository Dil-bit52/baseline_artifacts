#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import pandas as pd
import yaml


COLORS = {"high": "#2563EB", "medium": "#F59E0B", "low": "#DC2626"}


def q(value: pd.Series, probability: float) -> float:
    return float(value.quantile(probability))


def process_stats(path: Path) -> dict:
    frame = pd.read_csv(path)
    rss = pd.to_numeric(frame["rss_mb"], errors="coerce").dropna()
    cpu = pd.to_numeric(frame["cpu_percent_raw"], errors="coerce").dropna()
    return {
        "samples": int(len(frame)),
        "initial_rss_mib": float(rss.iloc[0]),
        "final_rss_mib": float(rss.iloc[-1]),
        "peak_rss_mib": float(rss.max()),
        "mean_cpu_percent": float(cpu.mean()),
        "peak_cpu_percent": float(cpu.max()),
    }


def frame_stats(path: Path) -> dict:
    frame = pd.read_csv(path)
    total = pd.to_numeric(frame["total_frame_ms"], errors="coerce").dropna()
    return {
        "frames": int(len(total)),
        "mean_total_frame_ms": float(total.mean()),
        "p95_total_frame_ms": q(total, 0.95),
        "p99_total_frame_ms": q(total, 0.99),
        "max_total_frame_ms": float(total.max()),
    }


def configure_plotting() -> None:
    chinese_font_path = Path(os.environ.get("STAGE2_CJK_FONT", "/tmp/stage2_msyh.ttc"))
    font_manager.fontManager.addfont(str(chinese_font_path))
    chinese_family = font_manager.FontProperties(fname=str(chinese_font_path)).get_name()
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": [chinese_family, "DejaVu Sans"],
        "axes.unicode_minus": False,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "font.size": 15,
        "axes.titlesize": 24,
        "axes.labelsize": 18,
        "legend.fontsize": 14,
        "xtick.labelsize": 14,
        "ytick.labelsize": 14,
    })


def footer(fig: plt.Figure, text: str) -> None:
    fig.text(0.012, 0.012, text, fontsize=10, color="#475569", ha="left", va="bottom")


def save(fig: plt.Figure, path: Path) -> None:
    fig.savefig(path, dpi=200, facecolor="white", bbox_inches="tight")
    plt.close(fig)


def make_pipeline_plot(path: Path, dot_path: Path, metrics: dict) -> None:
    count = metrics["lifecycle"]["total_tracked_voxels"]
    frames = metrics["lifecycle"]["frames"]
    dot = f'''digraph lifecycle {{
  graph [rankdir=LR, bgcolor="white", dpi=200, pad="0.5,2.0", nodesep=0.45, ranksep=0.6,
         label="B2 Passive Voxel Lifecycle Observer · AMtown01 全序列 {frames:,} 帧", labelloc=t,
         fontsize=28, fontname="Droid Sans Fallback", fontcolor="#0F172A"];
  node [shape=box, style="rounded,filled", fontname="Droid Sans Fallback", fontsize=18,
        penwidth=2.2, margin="0.22,0.16", color="#CBD5E1", fontcolor="#0F172A"];
  edge [color="#64748B", penwidth=2.5, arrowsize=1.0];
  a [label="世界系注册点云\\nfeats_down_world", fillcolor="#E0F2FE", color="#0284C7"];
  b [label="独立体素索引\\ns = 1.0 m", fillcolor="#ECFDF5", color="#059669"];
  c [label="生命周期更新\\n帧/命中/时间段", fillcolor="#FEF3C7", color="#D97706"];
  d [label="单序列内部\\n持久性代理分数", fillcolor="#EDE9FE", color="#7C3AED"];
  e [label="离线裁剪模拟\\n10%–50%", fillcolor="#FEE2E2", color="#DC2626"];
  a -> b -> c -> d -> e;
  note [shape=plain, fontsize=14, fontcolor="#475569", label="旁路观测：不反馈滤波器或 ikd-Tree · 最终体素 {count:,}"];
  {{rank=sink; note;}}
  c -> note [style=dashed, arrowhead=none, color="#94A3B8"];
}}'''
    dot_path.write_text(dot, encoding="utf-8")
    subprocess.run(["dot", "-Tpng", str(dot_path), "-o", str(path)], check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    args = parser.parse_args()
    root = args.workspace
    stage = root / "stage2_artifacts"
    run = stage / "raw" / "runs" / "b2_full_02"
    lifecycle_dir = run / "lifecycle"
    processed = stage / "processed"
    plots = stage / "plots"
    reports = stage / "reports"
    processed.mkdir(parents=True, exist_ok=True)
    plots.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)

    config = yaml.safe_load((stage / "config" / "persistence_analysis.yaml").read_text(encoding="utf-8"))["persistence_proxy"]
    summary = json.loads((lifecycle_dir / "lifecycle_run_summary.json").read_text(encoding="utf-8"))
    voxels = pd.read_csv(lifecycle_dir / "voxel_lifecycle_final.csv")
    frames = pd.read_csv(lifecycle_dir / "frame_lifecycle.csv")

    n_sat = float(config["n_sat"])
    t_sat = float(config["t_sat_sec"])
    bin_sec = float(config["time_bin_sec"])
    weights = config["weights"]
    w_c = float(weights["repeated_observation"])
    w_l = float(weights["lifespan"])
    w_d = float(weights["temporal_coverage"])
    origin = float(summary["sensor_start_time"])

    c_score = np.minimum(np.log1p(voxels["observed_frames"].to_numpy(dtype=np.float64)) / math.log1p(n_sat), 1.0)
    l_score = np.minimum(voxels["lifespan_sec"].to_numpy(dtype=np.float64) / t_sat, 1.0)
    first_bin = np.floor((voxels["first_seen_time"].to_numpy(dtype=np.float64) - origin) / bin_sec).astype(np.int64)
    last_bin = np.floor((voxels["last_seen_time"].to_numpy(dtype=np.float64) - origin) / bin_sec).astype(np.int64)
    lifecycle_bins = np.maximum(1, last_bin - first_bin + 1)
    d_score = np.clip(voxels["active_time_bins"].to_numpy(dtype=np.float64) / lifecycle_bins, 0.0, 1.0)
    p_score = np.clip(w_c * c_score + w_l * l_score + w_d * d_score, 0.0, 1.0)
    grouping = config["grouping"]
    if grouping["method"] == "quantiles":
        low_upper = float(np.quantile(p_score, float(grouping["low_quantile"])))
        medium_upper = float(np.quantile(p_score, float(grouping["high_quantile"])))
    else:
        low_upper = float(grouping["low_upper"])
        medium_upper = float(grouping["medium_upper"])
    groups = np.where(p_score < low_upper, "low", np.where(p_score < medium_upper, "medium", "high"))

    voxels["lifecycle_bins"] = lifecycle_bins
    voxels["C_v"] = c_score
    voxels["L_v"] = l_score
    voxels["D_v"] = d_score
    voxels["P_v"] = p_score
    voxels["persistence_group"] = groups
    score_path = processed / "voxel_persistence_scores.csv"
    voxels.to_csv(score_path, index=False, float_format="%.9f")

    group_rows = []
    total_hits = float(voxels["total_point_hits"].sum())
    for group in ("low", "medium", "high"):
        selected = voxels["persistence_group"] == group
        group_rows.append({
            "group": group,
            "voxel_count": int(selected.sum()),
            "voxel_share": float(selected.mean()),
            "point_hits": int(voxels.loc[selected, "total_point_hits"].sum()),
            "point_hit_share": float(voxels.loc[selected, "total_point_hits"].sum() / total_hits),
            "score_mean": float(voxels.loc[selected, "P_v"].mean()),
            "score_median": float(voxels.loc[selected, "P_v"].median()),
        })
    group_table = pd.DataFrame(group_rows)
    group_table.to_csv(processed / "persistence_group_summary.csv", index=False)

    order = np.lexsort((
        voxels["voxel_z"].to_numpy(), voxels["voxel_y"].to_numpy(),
        voxels["voxel_x"].to_numpy(), p_score,
    ))
    hits = voxels["total_point_hits"].to_numpy(dtype=np.int64)
    high = groups == "high"
    high_total = int(high.sum())
    xy_grid = float(config["xy_coverage_grid_m"])
    xy_x = np.floor(voxels["mean_x"].to_numpy(dtype=np.float64) / xy_grid).astype(np.int64)
    xy_y = np.floor(voxels["mean_y"].to_numpy(dtype=np.float64) / xy_grid).astype(np.int64)
    xy_cells = np.rec.fromarrays([xy_x, xy_y], names="x,y")
    original_xy_cells = int(np.unique(xy_cells).size)
    pruning_rows = []
    n = len(voxels)
    for fraction in config["pruning_fractions"]:
        fraction = float(fraction)
        remove_count = int(math.floor(n * fraction))
        remove_indices = order[:remove_count]
        retained_mask = np.ones(n, dtype=bool)
        retained_mask[remove_indices] = False
        retained_hits = int(hits[retained_mask].sum())
        retained_high = int(high[retained_mask].sum())
        retained_xy_cells = int(np.unique(xy_cells[retained_mask]).size)
        pruning_rows.append({
            "pruning_fraction": fraction,
            "original_voxels": n,
            "retained_voxels": int(retained_mask.sum()),
            "removed_voxels": remove_count,
            "voxel_retention_rate": float(retained_mask.mean()),
            "point_hit_retention_rate": retained_hits / total_hits,
            "high_persistence_retention_rate": retained_high / max(1, high_total),
            "map_scale_compression_proxy": fraction,
            "xy_grid_m": xy_grid,
            "original_xy_cells": original_xy_cells,
            "retained_xy_cells": retained_xy_cells,
            "xy_coverage_retention_rate": retained_xy_cells / max(1, original_xy_cells),
        })
    pruning = pd.DataFrame(pruning_rows)
    pruning.to_csv(processed / "pruning_simulation.csv", index=False)

    rng = np.random.default_rng(int(config["random_seed"]))
    sensitivity_sample = rng.choice(n, size=min(100000, n), replace=False)
    nominal_sample = p_score[sensitivity_sample]
    nominal_rank = pd.Series(nominal_sample).rank(method="average").to_numpy()
    sensitivity_rows = []
    cases = []
    for ns in (25.0, 50.0, 100.0):
        for ts in (150.0, 300.0, 600.0):
            cases.append((f"N_sat={int(ns)},T_sat={int(ts)}", ns, ts, w_c, w_l, w_d))
    cases.extend([
        ("recurrence_weight_emphasis", n_sat, t_sat, 0.6, 0.2, 0.2),
        ("lifespan_weight_emphasis", n_sat, t_sat, 0.25, 0.5, 0.25),
        ("coverage_weight_emphasis", n_sat, t_sat, 0.25, 0.25, 0.5),
    ])
    for name, ns, ts, wc, wl, wd in cases:
        cs = np.minimum(np.log1p(voxels["observed_frames"].to_numpy(dtype=np.float64)) / math.log1p(ns), 1.0)
        ls = np.minimum(voxels["lifespan_sec"].to_numpy(dtype=np.float64) / ts, 1.0)
        score = np.clip(wc * cs + wl * ls + wd * d_score, 0.0, 1.0)
        sample = score[sensitivity_sample]
        rank = pd.Series(sample).rank(method="average").to_numpy()
        alternate_groups = np.where(score < low_upper, "low", np.where(score < medium_upper, "medium", "high"))
        sensitivity_rows.append({
            "case": name, "n_sat": ns, "t_sat_sec": ts, "weight_c": wc, "weight_l": wl, "weight_d": wd,
            "low_upper": low_upper, "medium_upper": medium_upper,
            "low_share": float(np.mean(alternate_groups == "low")),
            "medium_share": float(np.mean(alternate_groups == "medium")),
            "high_share": float(np.mean(alternate_groups == "high")),
            "pearson_vs_nominal_sample": float(np.corrcoef(nominal_sample, sample)[0, 1]),
            "spearman_vs_nominal_sample": float(np.corrcoef(nominal_rank, rank)[0, 1]),
            "correlation_sample_size": int(len(sample)),
        })
    for lo, hi in ((0.25, 0.50), (0.33, 0.66), (0.40, 0.70)):
        alternate_groups = np.where(p_score < lo, "low", np.where(p_score < hi, "medium", "high"))
        sensitivity_rows.append({
            "case": f"thresholds={lo:.2f}/{hi:.2f}", "n_sat": n_sat, "t_sat_sec": t_sat,
            "weight_c": w_c, "weight_l": w_l, "weight_d": w_d, "low_upper": lo, "medium_upper": hi,
            "low_share": float(np.mean(alternate_groups == "low")),
            "medium_share": float(np.mean(alternate_groups == "medium")),
            "high_share": float(np.mean(alternate_groups == "high")),
            "pearson_vs_nominal_sample": 1.0, "spearman_vs_nominal_sample": 1.0,
            "correlation_sample_size": int(len(sensitivity_sample)),
        })
    sensitivity = pd.DataFrame(sensitivity_rows)
    sensitivity.to_csv(processed / "persistence_sensitivity.csv", index=False)

    b1_root = root / "baseline_artifacts" / "FAST_LIO2_ROS2_2fffc570_AMtown01_20260731" / "runs"
    b1_runs = []
    for run_id in ("performance_01", "performance_02", "performance_03"):
        fs = frame_stats(b1_root / run_id / "frame_metrics.csv")
        ps = process_stats(b1_root / run_id / "process_metrics.csv")
        b1_runs.append({"run_id": run_id, **fs, **ps})
    b1 = pd.DataFrame(b1_runs)
    b2_frame = frame_stats(run / "frame_metrics.csv")
    b2_process = process_stats(run / "process_metrics.csv")
    b1_mean_frame = float(b1["mean_total_frame_ms"].mean())
    observer = summary["observer_elapsed_ms"]
    b2_combined_mean = b2_frame["mean_total_frame_ms"] + float(observer["mean"])
    performance_rows = b1_runs + [{"run_id": "b2_full_02", **b2_frame, **b2_process}]
    pd.DataFrame(performance_rows).to_csv(processed / "performance_comparison.csv", index=False)

    metrics = {
        "dataset": {
            "name": "AMtown01_driver2",
            "sha256": summary["run_metadata"]["dataset_sha256"],
            "ground_truth_frozen": False,
        },
        "lifecycle": {
            "frames": int(summary["frames"]),
            "sensor_duration_sec": float(summary["sensor_duration_sec"]),
            "total_input_points": int(summary["total_input_points"]),
            "total_tracked_voxels": int(summary["total_tracked_voxels"]),
            "voxel_size_m": float(summary["config"]["voxel_size"]),
            "time_bin_sec": float(summary["config"]["time_bin_sec"]),
            "flush_interval_sec": float(summary["config"]["flush_interval_sec"]),
        },
        "persistence_proxy": {
            "name": config["name"], "n_sat": n_sat, "t_sat_sec": t_sat, "time_bin_sec": bin_sec,
            "weights": {"C": w_c, "L": w_l, "D": w_d},
            "grouping_method": grouping["method"], "low_upper": low_upper, "medium_upper": medium_upper,
            "score_mean": float(np.mean(p_score)), "score_median": float(np.median(p_score)),
            "score_p05": float(np.quantile(p_score, 0.05)), "score_p95": float(np.quantile(p_score, 0.95)),
            "groups": {row["group"]: row for row in group_rows},
        },
        "pruning": pruning_rows,
        "equivalence": json.loads((stage / "raw" / "runs" / "equivalence_b1_b2_02" / "equivalence.json").read_text(encoding="utf-8")),
        "smoke": {
            "disabled": json.loads((stage / "raw" / "runs" / "smoke_disabled_01" / "lifecycle_validation.json").read_text(encoding="utf-8")),
            "enabled_final": json.loads((stage / "raw" / "runs" / "smoke_enabled_02" / "lifecycle_validation.json").read_text(encoding="utf-8")),
        },
        "performance": {
            "observer_elapsed_ms": observer,
            "b2_core": b2_frame,
            "b2_process": b2_process,
            "b1_three_run_mean": {column: float(b1[column].mean()) for column in b1.columns if column != "run_id"},
            "combined_b2_mean_frame_proxy_ms": b2_combined_mean,
            "combined_mean_overhead_vs_b1_percent": (b2_combined_mean / b1_mean_frame - 1.0) * 100.0,
            "peak_rss_difference_vs_b1_mean_mib": b2_process["peak_rss_mib"] - float(b1["peak_rss_mib"].mean()),
            "limitations": "B2 has one full run; B1 comparison uses three prior full runs under the same dataset/config class but default multithread scheduling is nondeterministic. The combined frame proxy adds separately timed core and observer means.",
        },
        "failed_trials": [json.loads((stage / "raw" / "runs" / "b2_full_01" / "failure_summary.json").read_text(encoding="utf-8"))],
        "artifacts": {
            "voxel_scores_csv": str(score_path),
            "pruning_csv": str(processed / "pruning_simulation.csv"),
            "sensitivity_csv": str(processed / "persistence_sensitivity.csv"),
        },
    }
    (reports / "stage2_metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    configure_plotting()
    make_pipeline_plot(plots / "12_lifecycle_pipeline.png", processed / "12_lifecycle_pipeline.dot", metrics)

    fig, ax = plt.subplots(figsize=(16, 9))
    bins = np.linspace(0.0, 1.0, 81)
    ax.axvspan(0, low_upper, color=COLORS["low"], alpha=0.08, label="低持久性")
    ax.axvspan(low_upper, medium_upper, color=COLORS["medium"], alpha=0.10, label="中持久性")
    ax.axvspan(medium_upper, 1.0, color=COLORS["high"], alpha=0.08, label="高持久性")
    ax.hist(p_score, bins=bins, color="#475569", edgecolor="white", linewidth=0.5)
    ax.axvline(low_upper, color=COLORS["low"], linestyle="--", linewidth=2)
    ax.axvline(medium_upper, color=COLORS["high"], linestyle="--", linewidth=2)
    ax.set_title("单序列内部持久性代理分数分布")
    ax.set_xlabel("持久性代理分数 $P_v$")
    ax.set_ylabel("体素数量")
    ax.legend(loc="upper right")
    ax.grid(axis="y", alpha=0.2)
    footer(fig, f"数据源：b2_full_02/voxel_lifecycle_final.csv · N={n:,} · 30%/70% 分位阈值 {low_upper:.3f}/{medium_upper:.3f}")
    save(fig, plots / "13_persistence_score_distribution.png")

    fig, ax = plt.subplots(figsize=(16, 9))
    x = pruning["pruning_fraction"].to_numpy() * 100.0
    ax.plot(x, pruning["voxel_retention_rate"] * 100.0, marker="o", linewidth=3, label="体素保留率")
    ax.plot(x, pruning["point_hit_retention_rate"] * 100.0, marker="s", linewidth=3, label="点命中数保留率")
    ax.plot(x, pruning["high_persistence_retention_rate"] * 100.0, marker="^", linewidth=3, label="高持久性体素保留率")
    ax.plot(x, pruning["xy_coverage_retention_rate"] * 100.0, marker="D", linewidth=2, linestyle="--", label=f"XY {xy_grid:g} m 网格覆盖保留率")
    ax.set_title("离线低分体素裁剪：保留率曲线")
    ax.set_xlabel("移除最低分体素比例 (%)")
    ax.set_ylabel("保留率 (%)")
    ax.set_xticks(x)
    ax.set_ylim(0, 103)
    ax.grid(alpha=0.25)
    ax.legend(loc="lower left")
    footer(fig, "数据源：processed/pruning_simulation.csv · 体素下降是地图规模代理，不等同于实际内存节省")
    save(fig, plots / "14_retention_pruning_curve.png")

    sample_size = min(int(config["spatial_plot_max_points"]), n)
    spatial_indices = rng.choice(n, size=sample_size, replace=False)
    spatial = voxels.iloc[spatial_indices].sample(frac=1.0, random_state=int(config["random_seed"]))
    fig, (ax_full, ax_zoom) = plt.subplots(1, 2, figsize=(16, 9))
    for group in ("low", "medium", "high"):
        selected = spatial["persistence_group"] == group
        for ax in (ax_full, ax_zoom):
            ax.scatter(spatial.loc[selected, "mean_x"], spatial.loc[selected, "mean_y"], s=1.6,
                       c=COLORS[group], alpha=0.40, linewidths=0, label=f"{group} ({int(selected.sum()):,})")
    ax_full.set_title("全范围（保留离群点）")
    ax_zoom.set_title("中心 95% 范围放大")
    x_limits = np.quantile(voxels["mean_x"], [0.025, 0.975])
    y_limits = np.quantile(voxels["mean_y"], [0.025, 0.975])
    ax_zoom.set_xlim(x_limits)
    ax_zoom.set_ylim(y_limits)
    for ax in (ax_full, ax_zoom):
        ax.set_xlabel("X (m, camera_init)")
        ax.set_ylabel("Y (m, camera_init)")
        ax.set_aspect("equal", adjustable="datalim")
        ax.grid(alpha=0.15)
    ax_zoom.legend(markerscale=5, loc="best")
    fig.suptitle("生命周期体素的 XY 空间持久性分布", fontsize=25, y=0.99)
    footer(fig, f"数据源：processed/voxel_persistence_scores.csv · 固定种子 {config['random_seed']} 均匀随机抽样 {sample_size:,}/{n:,} · 右图仅缩放视野，左图保留全部范围")
    save(fig, plots / "15_spatial_persistence_xy.png")

    counts = voxels["observed_frames"].to_numpy(dtype=np.int64)
    max_count = int(counts.max())
    log_bins = np.unique(np.maximum(1, np.geomspace(1, max_count + 1, 70).astype(int)))
    fig, ax = plt.subplots(figsize=(16, 9))
    ax.hist(counts, bins=log_bins, color="#0EA5E9", edgecolor="white", linewidth=0.4)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_title("体素重复观测帧数分布")
    ax.set_xlabel("observed_frames（对数刻度）")
    ax.set_ylabel("体素数量（对数刻度）")
    ax.grid(alpha=0.2, which="both")
    footer(fig, f"数据源：b2_full_02/voxel_lifecycle_final.csv · N={n:,}")
    save(fig, plots / "16_voxel_observation_count_distribution.png")

    elapsed_min = (frames["timestamp"] - frames["timestamp"].iloc[0]) / 60.0
    rolling_new = frames["new_voxels"].rolling(100, min_periods=1).mean()
    fig, ax1 = plt.subplots(figsize=(16, 9))
    ax1.plot(elapsed_min, frames["total_tracked_voxels"], color="#2563EB", linewidth=2.5, label="累计体素")
    ax1.set_xlabel("传感器时间 (min)")
    ax1.set_ylabel("累计跟踪体素数量", color="#2563EB")
    ax1.tick_params(axis="y", labelcolor="#2563EB")
    ax2 = ax1.twinx()
    ax2.plot(elapsed_min, rolling_new, color="#F59E0B", linewidth=1.8, alpha=0.85, label="每帧新体素（100 帧滑动均值）")
    ax2.set_ylabel("每帧新体素数量", color="#F59E0B")
    ax2.tick_params(axis="y", labelcolor="#F59E0B")
    ax1.set_title("生命周期体素随时间累积")
    lines = ax1.get_lines() + ax2.get_lines()
    ax1.legend(lines, [line.get_label() for line in lines], loc="upper left")
    ax1.grid(alpha=0.2)
    footer(fig, "数据源：b2_full_02/frame_lifecycle.csv · 新体素曲线仅平滑用于趋势显示，数值统计使用原始帧")
    save(fig, plots / "17_lifecycle_over_time.png")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 9))
    latency_labels = ["均值", "P95", "峰值"]
    latency_values = [observer["mean"], observer["p95"], observer["max"]]
    ax1.bar(latency_labels, latency_values, color=["#0EA5E9", "#2563EB", "#DC2626"])
    ax1.set_yscale("log")
    ax1.set_ylabel("观测器耗时 (ms, 对数刻度)")
    ax1.set_title("B2 旁路观测器耗时")
    for i, value in enumerate(latency_values):
        ax1.text(i, value * 1.08, f"{value:.3f}", ha="center", fontsize=13)
    b1_peak = float(b1["peak_rss_mib"].mean())
    resource_labels = ["B1 核心帧均值", "B2 核心帧均值", "B2 核心+观测器", "B1 峰值RSS/100", "B2 峰值RSS/100"]
    resource_values = [b1_mean_frame, b2_frame["mean_total_frame_ms"], b2_combined_mean, b1_peak / 100.0, b2_process["peak_rss_mib"] / 100.0]
    ax2.barh(resource_labels, resource_values, color=["#64748B", "#0EA5E9", "#2563EB", "#A78BFA", "#7C3AED"])
    ax2.set_xlabel("帧耗时 (ms)；RSS 条目单位为 100 MiB")
    ax2.set_title("B1/B2 性能与 RSS 对照")
    for i, value in enumerate(resource_values):
        ax2.text(value + max(resource_values) * 0.015, i, f"{value:.2f}", va="center", fontsize=12)
    footer(fig, "数据源：B1 performance_01–03 与 B2 b2_full_02 · 默认多线程有非确定性；B2 仅一次完整运行")
    save(fig, plots / "18_b2_overhead.png")

    print(json.dumps({
        "voxel_count": n,
        "score_mean": metrics["persistence_proxy"]["score_mean"],
        "groups": {row["group"]: row["voxel_count"] for row in group_rows},
        "b2_peak_rss_mib": b2_process["peak_rss_mib"],
        "combined_overhead_percent": metrics["performance"]["combined_mean_overhead_vs_b1_percent"],
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
