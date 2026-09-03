#!/usr/bin/env python3
"""Remove non-runtime wheel baggage and build paths from a frozen onedir tree."""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

_ABSOLUTE_PATHS = (
    re.compile(
        r"(?<![A-Za-z0-9_:/])/(?:root|home|mnt|tmp|workspace|workspaces|Users|opt|srv|var|run|build|builds|agent|runner|project|repo|repos|checkout|checkouts|code|src|work)/"
        r"[^\x00\r\n\t \"'<>]+"
    ),
    re.compile(
        r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/]"
        r"[^\x00\r\n\t \"'<>]+"
    ),
)


def sanitize(root: Path) -> dict[str, int]:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"frozen tree is missing: {root}")
    removed = 0
    sanitized = 0
    for relative in (
        "pyarrow/tests",
        "pyarrow/src",
        "pyarrow/include",
        "pyarrow/includes",
        "boto3/examples",
        "jsonschema/benchmarks",
    ):
        for target in root.rglob(relative):
            if target.is_dir():
                shutil.rmtree(target)
                removed += 1
    for metadata in root.rglob("*.dist-info/METADATA"):
        text = metadata.read_text(encoding="utf-8", errors="replace")
        portable = text
        for pattern in _ABSOLUTE_PATHS:
            portable = pattern.sub("<build-path-omitted>", portable)
        if portable != text:
            metadata.write_text(portable, encoding="utf-8")
            sanitized += 1
    return {"removed_directories": removed, "sanitized_metadata": sanitized}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    print(sanitize(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
