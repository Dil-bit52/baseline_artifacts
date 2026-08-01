#!/usr/bin/env python3
import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git(source: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(source), *args], text=True).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_directory", type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--dataset-sha256", required=True)
    args = parser.parse_args()

    path = args.run_directory / "lifecycle" / "lifecycle_run_summary.json"
    summary = json.loads(path.read_text(encoding="utf-8"))
    summary["run_metadata"] = {
        "run_id": args.run_id,
        "dataset": "AMtown01_driver2",
        "dataset_path": str(args.dataset),
        "dataset_sha256": args.dataset_sha256,
        "source_git_head": git(args.source, "rev-parse", "HEAD"),
        "source_git_branch": git(args.source, "branch", "--show-current"),
        "source_git_status_porcelain": git(args.source, "status", "--short", "--ignore-submodules=all"),
        "binary_path": str(args.binary),
        "binary_sha256": sha256(args.binary),
        "build_type": "Release",
        "ros_distribution": "Humble",
    }
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


if __name__ == "__main__":
    main()
