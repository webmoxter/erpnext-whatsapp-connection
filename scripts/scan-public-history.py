#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess


PATTERNS = {
    "private key material": re.compile(
        "BEGIN " + r"(?:RSA |OPENSSH |EC )?PRIVATE KEY", re.IGNORECASE
    ),
    "AWS secret assignment": re.compile(
        "aws_secret_" + r"access_key\s*[:=]", re.IGNORECASE
    ),
    "generic client secret assignment": re.compile(
        "client_" + r"secret\s*[:=]", re.IGNORECASE
    ),
    "ERPFin360 production hostname": re.compile(
        r"(?:tfo|gac|premcorp)\." + "erpfin360" + r"\.com", re.IGNORECASE
    ),
    "ERPFin360 production account identifier": re.compile("037547" + "369922"),
}


def main() -> int:
    history = subprocess.run(
        ["git", "log", "-p", "--all", "--no-ext-diff"],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout
    failures = [label for label, pattern in PATTERNS.items() if pattern.search(history)]
    if failures:
        raise SystemExit("public-history scan failed: " + ", ".join(failures))
    print("PUBLIC_HISTORY_SECRET_SCAN=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

