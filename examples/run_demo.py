#!/usr/bin/env python3
"""End-to-end offline demo: ingest -> stitch -> consent -> segment -> activate -> erase.

    python examples/run_demo.py

The same synthetic person arrives as an anonymous web visitor, a
mobile signup and a CRM record; deterministic stitching unifies them.
A marketing activation is consent-gated, a profile is erased, and
data quality checks run over the final store.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from customer_data_platform.demo import run_demo  # noqa: E402


def main() -> int:
    report = run_demo()
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["demo_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
