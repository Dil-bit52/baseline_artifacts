# FAST-LIO2 ROS2 frozen baseline archive

The 33 GB source dataset is intentionally not duplicated here.  Its staged path is
`/data/fastlio_baseline/datasets/AMtown01_driver2`; file hashes and rosbag metadata
are under `dataset/`.  B0 and B1 source histories are stored as Git bundles.  Large
PCD and low-bandwidth output bags are retained under their immutable run IDs.

`private/` contains raw local environment evidence and must not be published.
Use only `public_redacted/` in papers, slides, or public repositories.
