#!/usr/bin/env python3
"""Render a deterministic top-down preview from the exported binary PCD.

This is a display-only stride sample.  It is not used for any numeric result.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np


PCD = Path("/data/fastlio_baseline/runs/map_export_01/registered_scan_aggregation.pcd")
OUT = Path("/workspace/baseline_artifacts/analysis/plots/12_map_topdown_stride_preview.png")
CHINESE_FONT = "/tmp/simhei.ttf"  # local render dependency; not archived
font_manager.fontManager.addfont(CHINESE_FONT)
plt.rcParams["font.family"] = font_manager.FontProperties(fname=CHINESE_FONT).get_name()
plt.rcParams["axes.unicode_minus"] = False


def read_header(path: Path) -> tuple[int, int]:
    points = None
    with path.open("rb") as handle:
        while True:
            line = handle.readline()
            if not line:
                raise ValueError("PCD DATA line not found")
            decoded = line.decode("ascii").strip()
            if decoded.startswith("POINTS "):
                points = int(decoded.split()[1])
            if decoded == "DATA binary":
                if points is None:
                    raise ValueError("PCD POINTS line not found")
                return points, handle.tell()


def main() -> None:
    points, offset = read_header(PCD)
    dtype = np.dtype(
        [
            ("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("intensity", "<f4"),
            ("normal_x", "<f4"), ("normal_y", "<f4"), ("normal_z", "<f4"), ("curvature", "<f4"),
        ]
    )
    cloud = np.memmap(PCD, dtype=dtype, mode="r", offset=offset, shape=(points,))
    stride = max(1, points // 100_000)
    sample = cloud[::stride]
    finite = np.isfinite(sample["x"]) & np.isfinite(sample["y"]) & np.isfinite(sample["z"])
    sample = sample[finite]
    fig, ax = plt.subplots(figsize=(10, 8))
    scatter = ax.scatter(sample["x"], sample["y"], c=sample["z"], s=0.25, cmap="viridis", alpha=0.65, rasterized=True)
    ax.set_aspect("equal", adjustable="box")
    ax.set_title(f"AMtown01 注册扫描聚合 PCD 俯视图（显示用：每 {stride} 点取 1 点）")
    ax.set_xlabel("x（m）")
    ax.set_ylabel("y（m）")
    ax.grid(True, alpha=0.18)
    fig.colorbar(scatter, ax=ax, label="z（m）")
    fig.tight_layout()
    fig.savefig(OUT, dpi=220, bbox_inches="tight")
    fig.savefig(OUT.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)
    print(f"points={points} stride={stride} rendered={len(sample)} output={OUT}")


if __name__ == "__main__":
    main()
