# FAST-LIO2 ROS2 基线复现与实验环境冻结

## 左侧：环境和数据

- ROS 2 Humble / `rmw_fastrtps_cpp`
- Ubuntu 22.04.5，Docker `osrf/ros:humble-desktop`
- CPU：i5-14600K，容器可见 20 线程 / 7.6 GiB
- FAST-LIO2：`2fffc570`；B1：`6d82e21`
- AMtown01：22.573 min，MCAP 33.009 GB
- LiDAR：13,543 帧、约 10 Hz；IMU：281,894 条、约 208 Hz
- 无已冻结 GT：ATE/RPE = N/A

## 中间：运行流程

```text
ROS2 MCAP（/data，1.0×）
        ↓
LiDAR CustomMsg + IMU
        ↓
预处理 / IMU 传播与去畸变
        ↓
Scan-to-Map + ESIKF
        ↓
ikd-Tree 增量地图
        ↓
Odometry + TF + 帧级 CSV
```

正式性能配置关闭 Path、全部非必需点云、PCD 与 RViz；地图与可视化独立运行。

## 右侧：核心结果（3 次均值 ± 样本标准差）

- 完成率：3/3；每次 13,334 帧，无 NaN/崩溃
- 平均 CPU：60.045 ± 0.394%；峰值 CPU：130.462 ± 10.994%
- 峰值 RSS：723.549 ± 55.785 MiB
- RSS 斜率：15.571 ± 2.545 MiB/min；平均回归 R2=0.518
- 结束 ikd-Tree：783,665 ± 114,062 点
- 地图斜率：15,146 ± 3,611 points/min
- 帧耗时：均值 14.028 ± 0.106 ms；P95 17.963 ± 0.143 ms
- 有效窗口最大 backlog：0.501 ± 0.519 s；drain 3.035 s
- 轨迹长度：4916.967 ± 0.746 m（不是精度）
- RSS–地图点数 Pearson r：0.645 ± 0.050（相关，不代表因果）

## 推荐配图

- 主图：`analysis/plots/02_rss_over_time.png`
- 辅图：`analysis/plots/03_kdtree_points_over_time.png`
- 风险图：`analysis/plots/08_three_run_comparison.png`
- 地图图：`analysis/plots/12_map_topdown_stride_preview.png`

## 底部结论

已冻结 B0/B1 源码、二进制、配置、真实数据和统一测量链路。耗时重复性良好，但默认 ROS/OpenMP 调度下轨迹与地图规模存在显著非确定性；后续地图管理对比必须固定调度、保留三次以上重复，并补充具有明确对齐协议的 GT 数据集。
