# 阶段 2 可复现命令

所有 ROS2 命令在 `carry_bot_container` 内执行；主机工作区绑定到 `/workspace`。下列命令不会写入阶段 1 冻结目录。

## 1. 最终 B2 构建

```powershell
docker exec carry_bot_container bash -lc "bash /workspace/stage2_artifacts/scripts/build_b2.sh build_04"
```

核心构建命令：

```bash
source /opt/ros/humble/setup.bash
cd /workspace/stage2_workspaces/b2
colcon --log-base log build \
  --base-paths src --build-base build --install-base install \
  --packages-up-to fast_lio --event-handlers console_direct+ \
  --cmake-args -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
  -DROS_EDITION=ROS2 -DDISTRO_ROS=humble
```

## 2. 关闭/开启冒烟

```powershell
docker exec carry_bot_container bash -lc "bash /workspace/stage2_artifacts/scripts/run_b2.sh smoke_disabled_01 45 disabled 1.0 57"
docker exec carry_bot_container bash -lc "bash /workspace/stage2_artifacts/scripts/run_b2.sh smoke_enabled_02 90 enabled 1.0 61"
```

## 3. 最终 B1/B2 受控等价性

```powershell
docker exec carry_bot_container bash -lc "bash /workspace/stage2_artifacts/scripts/run_b1_b2_equivalence.sh equivalence_b1_b2_02 180 62"
```

该脚本使用同一 bag 播放器、`--rate 0.1`、`OMP_THREAD_LIMIT=1`，记录 `/b1/Odometry` 和 `/b2/Odometry`，再按纳秒时间戳比较。

## 4. AMtown01 完整序列

```powershell
docker exec carry_bot_container bash -lc "bash /workspace/stage2_artifacts/scripts/run_b2.sh b2_full_02 full enabled 1.0 63"
```

播放器核心命令：

```bash
ros2 bag play /data/fastlio_baseline/datasets/AMtown01_driver2 \
  --clock --rate 1.0 --delay 5 --topics /livox/lidar /livox/imu
```

## 5. 生命周期一致性检查

```bash
python3 /workspace/stage2_artifacts/scripts/validate_lifecycle.py \
  /workspace/stage2_artifacts/raw/runs/b2_full_02
```

## 6. 持久性、裁剪、敏感性和绘图

中文字体只临时放在容器 `/tmp`，不归档：

```powershell
docker cp C:\Windows\Fonts\msyh.ttc carry_bot_container:/tmp/stage2_msyh.ttc
docker exec carry_bot_container bash -lc "STAGE2_CJK_FONT=/tmp/stage2_msyh.ttc python3 /workspace/stage2_artifacts/scripts/analyze_stage2.py --workspace /workspace"
```

## 7. 失败试验

`b2_full_01` 的原命令为：

```powershell
docker exec carry_bot_container bash -lc "bash /workspace/stage2_artifacts/scripts/run_b2.sh b2_full_01 full enabled 1.0 60"
```

该运行使用当时配置的 0.5 m 体素和旧检查点逻辑，已保留在 `stage2_artifacts/raw/runs/b2_full_01`，并由 `failure_summary.json` 明确标记未完成。
