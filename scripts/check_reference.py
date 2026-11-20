#!/usr/bin/env python3
"""Check that the vendored challenge files are byte-identical to the pinned release.

Hashes in reference/SHA256SUMS were copied from the benchmark's release manifest at commit
d87699bb97de6504b33f681eed66918a4d433ba0 (release 2026-09-07).
"""
import hashlib
import sys
from pathlib import Path

REF = Path(__file__).resolve().parent.parent / "reference"


def main() -> int:
    bad = 0
    for line in (REF / "SHA256SUMS").read_text().splitlines():
        if not line.strip():
            continue
        digest, name = line.split(maxsplit=1)
        name = name.lstrip("*").strip()
        actual = hashlib.sha256((REF / name).read_bytes()).hexdigest()
        if actual != digest:
            bad += 1
            print(f"MISMATCH {name}: expected {digest} got {actual}")
    print("reference files:", "OK" if not bad else f"{bad} mismatched")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
