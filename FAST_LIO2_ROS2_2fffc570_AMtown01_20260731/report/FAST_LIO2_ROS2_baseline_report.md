# FAST-LIO2 ROS2 基线复现与冻结实验报告

- 基线 ID：`FAST_LIO2_ROS2_2fffc570_AMtown01_20260731`
- 实验日期：2026-07-31（原始记录为 UTC，宿主时区 America/New_York）
- 阶段结论：P0 与 P1 已完成；RViz 图形链路失败但已按任务允许的离线 PCD/轨迹方案替代并保留证据；P2 的 Ground Truth/ATE/RPE 未完成。

## 1. 实验目的

本实验重新验证并冻结 FAST-LIO2 ROS2 环境、源码、依赖、配置和真实数据，建立不修改核心算法的 B0 Vanilla 与仅增加观测代码的 B1 Instrumentation。目标是给后续“地图元素持久性评估与几何可观测性约束”研究提供统一对照，不在本阶段加入论文创新算法。

## 2. 环境

| 项目 | 实测值 |
|---|---|
| 宿主 | Windows，Docker Desktop（daemon 29.4.0，WSL2 kernel 6.6.87.2） |
| 容器 | `dc3ae6023b26`（短 ID），运行中；创建于 2026-04-24 |
| 镜像 | `osrf/ros:humble-desktop`；ID/RepoDigest `sha256:327fe46e…490b` |
| 容器系统 | Ubuntu 22.04.5 LTS, x86_64 |
| ROS / RMW | ROS 2 Humble；环境变量未显式设置 RMW，`ros2 doctor` 实测 `rmw_fastrtps_cpp` |
| CPU | Intel Core i5-14600K；容器可见 20 个逻辑 CPU，无显式 CPU quota |
| 内存 | 容器可见 7.6 GiB；Docker inspect 未配置显式 memory limit |
| 编译工具 | GCC/G++ 11.4.0；CMake 3.22.1；Python 3.10.12 |
| 数值/点云依赖 | Eigen 3.4.0；PCL 1.12.1；OpenMP 由 GCC 工具链提供 |
| Livox | `livox_ros_driver2` 源码冻结；系统 `/usr/local/lib/liblivox_lidar_sdk_shared.so` 已解析并哈希 |
| 工作区 | Windows `/workspace` bind mount；正式构建与运行均位于容器 Linux `/data/fastlio_baseline` |

完整 Docker inspect/info 只存于 `private/`；报告使用的脱敏摘要位于 `public_redacted/`。公开摘要不含宿主源路径、用户名、环境变量值或代理凭据。

## 3. 源码版本

| 组件 | 仓库/分支 | 冻结提交 |
|---|---|---|
| FAST-LIO2 ROS2 B0 | Ericsii/FAST_LIO_ROS2，`ros2` | `2fffc570a25d0df172720bac034fbdb6a13d2162` |
| ikd-Tree 子模块 | B0 子模块 | `e2e3f4e9d3b95a9e66b1ba83dc98d4a05ed8a3c4` |
| livox_ros_driver2 | Livox-SDK/livox_ros_driver2 | `13eb05e4e6dd7a765b934d0c5fd6236676a57b49` |
| Livox-SDK2 | Livox-SDK/Livox-SDK2 | `22d98dcd4672953fbc96d6bc9f1be7a1c0cfef9e` |
| B1 本地提交 | `experiment/baseline-instrumentation` | `6d82e211f250a8b97c71eb8112d98e3ec29770ae` |

原工作树存在用户修改；在任何克隆/构建前已保存 branch、HEAD、remote、submodule、porcelain v2、worktree/index binary patch 和未跟踪文件清单，未执行 reset/clean。B0 是无 hardlink 的独立克隆、detached 到目标提交、子模块固定且干净。B1 由 B0 派生，修改仅在 `src/laserMapping.cpp`，补丁为 `instrumentation.patch`。

二进制 SHA-256：

- B0 `fastlio_mapping`：`6e2c9cd2a4df33f5dd1f5c7a0f0e357ffcd43a05fe93ffb08a6cc4c705c757d5`
- B1 `fastlio_mapping`：`d44ba02343650522f112764435d6e5f398456a22254a7363c691a12597adc10d`

## 4. 实际接口

源码、launch、`ros2 launch --show-args`、运行期 node/topic/parameter 快照共同确认：

| 类型 | 名称 | 消息/服务类型 | Frame | 用途 |
|---|---|---|---|---|
| 包/可执行 | `fast_lio` / `fastlio_mapping` | — | — | FAST-LIO2 ROS2 |
| 节点 | `/laser_mapping` | — | — | 主建图节点 |
| 输入 | `/livox/lidar` | `livox_ros_driver2/msg/CustomMsg` | 数据自带 | Livox Avia 点云 |
| 输入 | `/livox/imu` | `sensor_msgs/msg/Imu` | 数据自带 | IMU |
| 输出 | `/Odometry` | `nav_msgs/msg/Odometry` | `camera_init`，child `body` | 里程计 |
| 输出 | `/path` | `nav_msgs/msg/Path` | `camera_init` | 路径；性能配置关闭 |
| 输出 | `/cloud_registered` | `sensor_msgs/msg/PointCloud2` | `camera_init` | 注册扫描；非完整内部地图 |
| 输出 | `/cloud_registered_body` | `sensor_msgs/msg/PointCloud2` | `body` | 机体系注册扫描 |
| 输出 | `/cloud_effected` | `sensor_msgs/msg/PointCloud2` | `camera_init` | 有效点 |
| 输出 | `/Laser_map` | `sensor_msgs/msg/PointCloud2` | `camera_init` | 定时器聚合的注册扫描 |
| 服务 | `/map_save` | `std_srvs/srv/Trigger` | N/A | 保存聚合 PCD |
| TF | `camera_init → body` | TF2 | 两 frame | 位姿变换 |

launch 参数为 `config_path`、`config_file`、`use_sim_time`、`rviz`、`rviz_cfg`；实现会拼接配置目录与文件名，因此运行脚本分别传入目录和文件名。

## 5. 数据集

选择 MARS-LVIG 的 AMtown01。公开数据页面为 [DapengFeng/MCAP AMtown01](https://huggingface.co/datasets/DapengFeng/MCAP/tree/main/mars_lvig/AMtown01)，数据卡许可证为 CC BY-NC 4.0；数据集论文见 [MARS-LVIG DOI](https://doi.org/10.1177/02783649241227968)。本机原始副本使用旧 `livox_ros_driver/msg/CustomMsg`，正式实验使用本机已有的 driver2 派生副本；二者消息计数一致，但历史转换脚本不可追溯，因此不把 driver2 副本冒充官方原文件。

| 指标 | 实测值 |
|---|---:|
| 数据时长 | 1354.388754976 s（22.573 min，超过建议 5–20 min；为复用已存在真实完整序列而接受） |
| MCAP 大小 | 33,009,250,404 bytes |
| 总消息数 | 2,168,650 |
| `/livox/lidar` | 13,543；约 10 Hz；`livox_ros_driver2/msg/CustomMsg` |
| `/livox/imu` | 281,894；约 208 Hz；`sensor_msgs/msg/Imu` |
| LiDAR 点时间 | `offset_time`，单帧约 0–100 ms；逐点时序保留 |
| 外参 | T `[0.04165, 0.02326, -0.0284]` m；R 为单位阵；在线外参估计关闭 |
| MCAP SHA-256 | `6f3c85f54982d88d1dd2707815922e5a77fa7d64a787a608ac43d6a70f819586` |
| metadata SHA-256 | `b18d1f4b33e6c16d53f5192da78207930907e4efe4d19b0cd65609bffe40ece0` |
| Ground Truth | N/A：未冻结一条具有明确时间关联与坐标对齐协议的官方 GT |

兼容性检查确认 `point_num=72000`、字段定义正确、LiDAR/IMU 时间单调且重叠。尾部 96 帧中 69 帧为零有效点、70 帧少于 5 点；最后可处理 LiDAR 时间为 `1658138371.9247339`。因此原始最后 LiDAR 与最后里程计约 9.702 s 的差不是未排空积压。

## 6. 配置

四份配置均由仓库 `avia.yaml` 派生并单独哈希：

- Smoke：保留里程计及必要诊断输出，120 s。
- Performance：`path_en=false`，所有 registered/effect/map/body/dense 点云发布关闭，`pcd_save_en=false`，RViz=false；正式全 bag、1.0×。
- Map Export：独立启用 map 聚合和 PCD 保存，不进入性能统计。
- Visualization：独立启用可视化发布，RViz=true；只用于显示证据。

共同算法参数包括 `point_filter_num=3`、surface/map voxel 0.5 m、最大迭代 3、blind 4 m、Avia 6 线/10 Hz、det range 450 m、cube side 1000 m。B1 正式性能运行使用源码默认 `MP_PROC_NUM=3`，未使用等价审计的单线程设置。

## 7. 构建与运行命令

B0/B1 构建核心命令（分别在隔离工作区执行）：

```bash
source /opt/ros/humble/setup.bash
cd /data/fastlio_baseline/workspaces/b0   # B1 时改为 b1
colcon --log-base log build \
  --base-paths src --build-base build --install-base install \
  --packages-up-to fast_lio --event-handlers console_direct+ \
  --cmake-args -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
  -DROS_EDITION=ROS2 -DDISTRO_ROS=humble
```

B0/B1 构建退出码均为 0，wall-clock 分别为 54.331 s 与 55.485 s；`/usr/bin/time` 不存在，故脚本明确记录使用 `date +%s%N` fallback。最终 B0/B1 `ldd` 无 `not found`。

正式运行统一通过：

```powershell
docker exec carry_bot_container bash /workspace/baseline_artifacts/scripts/run_baseline.sh `
  b1 performance_01 performance full false
```

节点、播放与记录的核心参数：

```bash
export ROS_DOMAIN_ID=47
ros2 launch fast_lio mapping.launch.py \
  config_path:=<run_dir> config_file:=config.yaml use_sim_time:=true rviz:=false
ros2 bag play /data/fastlio_baseline/datasets/AMtown01_driver2 \
  --clock --rate 1.0 --delay 5 --topics /livox/lidar /livox/imu
ros2 bag record --storage mcap -o <run_dir>/estimated_odometry /Odometry /tf /tf_static
```

## 8. B0 结果

| 运行 | 结果 |
|---|---|
| B0 构建 | 成功；退出码 0；二进制动态库全部解析 |
| `b0_smoke_01` | 120 s；1,086 条 Odometry；轨迹 184.999 m；有限值、时间戳严格递增、四元数单位化 |
| `b0_full_01` | 全序列；13,334 条 Odometry；轨迹 4922.023 m；无 NaN/Inf、无崩溃 |
| B0 地图 | binary PCD；8,602,360 点；275,275,773 bytes；SHA-256 `882f2131…b9e4` |

B0 全序列的原始 drain 检查曾以数据最后声明 LiDAR 帧为目标而超时；随后保留原失败记录并通过逐帧尾部检查证明末尾没有可处理点，功能验收改用文档化的最后有效帧，没有固定 sleep，也没有删除异常数据。

## 9. B1 插桩与等价性

B1 增加 72 行，只负责同步原始点数、打开 `FASTLIO_METRICS_CSV`、缓冲写 CSV（每 100 帧 flush）和记录：传感器/墙钟时间、帧号、ikd-Tree 前后点数、插入/删除点数、原始/降采样/有效点数、最近邻/Scan-to-Map/ESIKF/地图插入删除更新/总帧耗时、LiDAR/IMU 缓冲长度。没有更改状态估计、残差、数据关联、降采样、插删规则、参数或发布位姿。

等价性历史不能被压缩成单一“通过”：

- 顺序 B0/B1 和 0.5× 同播放器双节点试验出现米级/角度级差异；B0 重复自身也分叉，说明该 ROS/OpenMP 调度下存在初始化/消息交付非确定性。
- 最终 `equivalence_simultaneous_03` 使用同一 bag 播放器、0.1×、5 s delay、`OMP_THREAD_LIMIT=1` 的确定性审计；B0/B1 各 63 条，时间戳完全匹配，最大/最终位置差 0 m，最大/最终旋转差 0°，通过 1 mm/0.01° 阈值。

因此结论是：**B1 在控制调度的审计窗口内严格等价，且补丁未表现出系统性偏差；默认多线程全序列不能宣称逐帧确定性等价。** 这是一项已记录的基线限制，而不是删除失败试验后的“无条件等价”。

## 10. 三次正式性能实验

三次均为 B1、全 AMtown01、1.0×、默认 3 线程、性能配置；另有一次 120 s `warmup_01`，不参与统计。三次全部成功，均产生 13,334 帧/轨迹点且无 NaN/Inf。

| 指标 | Run 1 | Run 2 | Run 3 | 均值 ± 样本标准差 |
|---|---:|---:|---:|---:|
| 进程平均 CPU (%) | 59.601 | 60.182 | 60.352 | 60.045 ± 0.394 |
| 进程峰值 CPU (%) | 117.821 | 137.797 | 135.767 | 130.462 ± 10.994 |
| 初始 RSS (MiB) | 142.969 | 142.500 | 142.969 | 142.813 ± 0.271 |
| 结束 RSS (MiB) | 597.648 | 618.480 | 692.438 | 636.189 ± 49.814 |
| 峰值 RSS (MiB) | 673.582 | 713.328 | 783.738 | 723.549 ± 55.785 |
| RSS 斜率 (MiB/min) | 14.057 | 14.145 | 18.509 | 15.571 ± 2.545 |
| RSS 回归 R2 | 0.574 | 0.429 | 0.550 | 0.518 ± 0.078 |
| 结束 ikd-Tree 点数 | 910,202 | 688,749 | 752,045 | 783,665 ± 114,062 |
| 地图斜率 (points/min) | 19,210 | 12,304 | 13,924 | 15,146 ± 3,611 |
| 单帧均值 (ms) | 13.907 | 14.070 | 14.106 | 14.028 ± 0.106 |
| 单帧 P95 (ms) | 17.808 | 18.091 | 17.991 | 17.963 ± 0.143 |
| 单帧 P99 (ms) | 21.272 | 21.337 | 21.010 | 21.206 ± 0.173 |
| 有效窗口最大 backlog (s) | 1.100 | 0.202 | 0.200 | 0.501 ± 0.519 |
| 原始最大 clock lag (s) | 9.970 | 9.970 | 9.975 | 9.971 ± 0.003 |
| drain time (s) | 3.035 | 3.035 | 3.035 | 3.035 ± 0.0004 |
| 轨迹长度 (m；非精度) | 4917.501 | 4916.115 | 4917.285 | 4916.967 ± 0.746 |

Odometry 平均输出频率约 10.00 Hz。10 Hz LiDAR 周期为 100 ms，而最大单帧耗时为 78.657 ms；帧级 LiDAR buffer 峰值 1、IMU buffer 峰值 40。有效数据窗口出现一次 Run 1 的约 1.1 s 延迟，但最终自然排空；尾部约 9.7 s 的 raw backlog/clock lag 来自无有效点帧，不能解释为持续算法积压。

RSS 与墙钟对齐后的 ikd-Tree 点数 Pearson r 分别为 0.620、0.703、0.613，均值 0.645；仅说明本数据和参数下存在中等正相关趋势，不证明地图增长导致内存变化。RSS 回归只使用完整序列、未裁剪初始化、约 2,728 个进程样本/次；阶梯式释放和 R2≈0.52 不支持据此直接宣称内存泄漏。

内部耗时字段显示 Scan-to-Map 均值约 8.97 ms、ESIKF update 均值约 9.93 ms、地图 update 均值约 2.89 ms。`nearest_search_ms` 在三次运行均为 0：B1 正确导出了上游 `kdtree_search_time`，但该提交未单独累积此变量，因此该列是**已知插桩可观测性缺口**，不能解释为最近邻搜索零开销。

三次默认多线程轨迹长度接近，但 XY 形状与结束地图点数明显不同；轨迹长度不是定位精度。ATE/RPE = N/A，因为没有已冻结且有时间/坐标对齐协议的 GT。

## 11. 地图与可视化

独立 `map_export_01` 成功，所有组件与 `/map_save` 退出码为 0，服务返回 `success=True, message='Map saved.'`。B1 PCD 为 binary、8,590,275 点、274,889,053 bytes，SHA-256 `b2fe3fdcece1f4291f006e6cdd06dfd70d888907e4531085963126b720859dbe`。该文件是注册扫描聚合，不是 ikd-Tree 全部内部节点的直接导出。

独立 `visualization_01` 启动了 RViz，但 Qt 无法连接既有 `DISPLAY=host.docker.internal:0.0`，RViz 以 `-6` 退出；FAST-LIO2 节点和记录仍完成。未修改全局 DISPLAY，也未伪造 RViz 截图。按任务允许的降级方案，提供真实轨迹图、PCD 固定步长俯视预览、节点/话题/参数快照、`ros2 bag info` 和终端日志。PCD 图每 85 点显示 1 点，仅用于渲染，不参与数值统计。

## 12. 问题与修复

| 现象 | 根因 | 修复 | 是否影响算法 | 验证结果 |
|---|---|---|---|---|
| `/usr/bin/time` 不存在 | 镜像未安装 | 记录 wall-clock fallback | 否 | B0/B1 build rc=0，方法写入 `build_time.txt` |
| driver 构建缺 `package.xml` | 上游以 `package_ROS2.xml`/`launch_ROS2` 分发 | 仅在独立 driver 克隆中按官方 ROS2 布局生成 | 否 | driver/fast_lio 均构建通过 |
| 构建缺发行版定义 | driver CMake 需要 ROS2/Humble 宏 | 加 `-DROS_EDITION=ROS2 -DDISTRO_ROS=humble` | 否 | clean isolated build 通过 |
| 首版错误扫描误命中 INFO | 简单 `inf` 正则 | 改为非有限值边界模式 | 否 | Smoke/Full 有限值检查通过 |
| Full drain 初版超时 | bag 尾部零/极少点 | 保留原失败；逐帧审计并用最后有效帧作为排空目标 | 否 | 三次正式 run drain rc=0 |
| 默认调度 B0/B1/重复运行分叉 | ROS 消息交付与 OpenMP 非确定性 | 增加同播放器、单线程、0.1× 控制审计 | 否 | 审计窗口 0 m/0°；默认多线程风险保留 |
| RViz 启动失败 | 宿主 X server 不可达 | 不改 DISPLAY；使用离线 PCD/轨迹图 | 否 | 算法与 map export 成功；RViz 限制有日志证据 |
| 最近邻耗时为 0 | 上游变量未单独累积 | 不伪造；标为可观测性缺口 | 否 | CSV 字段存在，报告不将 0 解释为真实成本 |

## 13. 阶段结论

1. FAST-LIO2 ROS2 已成功复现：B0 隔离构建、启动、120 s smoke 和全序列均成功。
2. B0 完整输出 Odometry、CSV/TUM 轨迹、日志和聚合地图，无 NaN、崩溃或无法解释的最终积压。
3. B1 在控制调度的等价审计中与 B0 严格相同；默认多线程全序列不具有逐帧确定性，不能作无条件等价声明。
4. 三次性能实验均完成且帧耗时重复性好，但轨迹形状、结束地图点数与 RSS 峰值存在显著运行间变异。
5. AMtown01 适合验证流水线、资源/地图增长和调度敏感性；因 driver2 转换历史不完整、无冻结 GT、默认轨迹分叉，不适合作为单一精度结论数据集。
6. ikd-Tree 点数随时间非单调增长并因局部地图删除产生阶梯下降；整段线性斜率仍为正。
7. RSS 与地图点数存在中等正相关趋势（平均 r=0.645），不能据此认定因果或内存泄漏。
8. 有效窗口内没有持续无法排空的实时积压；Run 1 曾出现约 1.1 s 峰值，三次最终均排空。
9. 当前不足：无冻结 GT/ATE/RPE；driver2 转换过程不可追溯；最近邻独立耗时变量未填充；RViz X 链路不可用；默认多线程轨迹非确定性；单数据集、约 22.6 min 不能证明长期行为。

后续阶段建议固定同一 B1 观测接口，优先补充带明确 GT/对齐协议的数据集；将线程/执行器/ROS QoS 固定为实验因素；增加 voxel 生命周期、重观测次数和局部信息矩阵特征值，同时以更长重复路线验证 RSS/地图规模趋势。

## 验收摘要

- P0：全部满足。
- P1：除 RViz 图形链路本身不可用外，其余满足；按任务规定已提供限制说明和离线 PCD/轨迹替代，因此阶段 1 可接受。
- P2：未执行 GT/ATE/RPE；已额外导出 PDF 图与 typed XLSX 结果工作簿。
- 所有表格和图来自真实运行；未平滑、未剔除异常点、未填造数据。
