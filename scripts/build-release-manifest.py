#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 5:
        raise SystemExit(
            "usage: build-release-manifest.py <tag> <commit> <gateway-image@digest> <asset>..."
        )
    tag, commit, gateway_image, *filenames = sys.argv[1:]
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        raise SystemExit("invalid semantic release tag")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise SystemExit("invalid source commit")
    if not re.fullmatch(r"ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+@sha256:[0-9a-f]{64}", gateway_image):
        raise SystemExit("gateway image is not digest-pinned")
    assets = {}
    for filename in sorted(filenames):
        path = Path(filename)
        if not path.is_file():
            raise SystemExit(f"missing release asset: {filename}")
        assets[path.name] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size": path.stat().st_size,
        }
    manifest = {
        "schema_version": 1,
        "release": tag.removeprefix("v"),
        "source_commit": commit,
        "gateway_image": gateway_image,
        "assets": assets,
    }
    Path("release-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
