# FAST-LIO2 ROS2 baseline — PPT data tables

All values below are generated from the three accepted formal runs without smoothing or outlier removal.

| Metric | 3-run mean | sample std | unit |
|---|---:|---:|---|
| total_frame_ms_mean | 14.027753 | 0.106326 | ms |
| total_frame_ms_p95 | 17.963284 | 0.143250 | ms |
| total_frame_ms_p99 | 21.206168 | 0.173316 | ms |
| rss_mib_peak | 723.549333 | 55.784790 | MiB |
| rss_mib_slope_per_min | 15.570579 | 2.545215 | MiB/min |
| kdtree_points_final | 783665.333333 | 114062.447424 | points |
| trajectory_path_length_m | 4916.967130 | 0.745984 | m |
| sensor_backlog_sec_max_valid_window | 0.500581 | 0.519136 | s |

| Run | frames | path (m) | frame P95 (ms) | peak RSS (MiB) | final tree points |
|---|---:|---:|---:|---:|---:|
| performance_01 | 13334 | 4917.501 | 17.808 | 673.582 | 910202 |
| performance_02 | 13334 | 4916.115 | 18.091 | 713.328 | 688749 |
| performance_03 | 13334 | 4917.285 | 17.991 | 783.738 | 752045 |
