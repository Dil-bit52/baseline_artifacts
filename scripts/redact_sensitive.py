#!/usr/bin/env python3
"""Redact likely credentials from environment/inspection text before publication."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


SENSITIVE = re.compile(
    r"(?i)(token|password|passwd|secret|api[_-]?key|private[_-]?key|cookie|authorization|proxy[_-]?(?:user|password))"
)
ASSIGNMENT = re.compile(r"^([^:=\s]+)\s*([:=])\s*(.*)$")


def redact_line(line: str) -> str:
    match = ASSIGNMENT.match(line.rstrip("\n"))
    if match and SENSITIVE.search(match.group(1)):
        return f"{match.group(1)}{match.group(2)}<REDACTED>\n"
    if SENSITIVE.search(line):
        return "<REDACTED_SENSITIVE_LINE>\n"
    return line


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.input.open("r", encoding="utf-8", errors="replace") as source:
        with args.output.open("w", encoding="utf-8", newline="") as target:
            for line in source:
                target.write(redact_line(line))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
