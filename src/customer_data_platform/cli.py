"""Command-line interface.

    customer-data-platform demo          run the end-to-end demo
    customer-data-platform profiles      list unified profiles (demo data)
    customer-data-platform quality       quality summary (demo data)
    customer-data-platform serve [--port N]  run the FastAPI service
"""
from __future__ import annotations

import argparse
import json

from .demo import build_demo_platform, run_demo
from .service import CDPService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="customer-data-platform", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="run the end-to-end demo")
    sub.add_parser("profiles", help="list profiles from the demo scenario")
    sub.add_parser("quality", help="quality summary from the demo scenario")
    serve = sub.add_parser("serve", help="run the FastAPI service")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    if args.command == "demo":
        print(json.dumps(run_demo(), indent=2, default=str))
        return 0
    if args.command == "profiles":
        report = build_demo_platform()
        print(json.dumps({"alex_profile_id": report["alex_profile_id"],
                          "alex_identifiers": report["alex_identifiers"],
                          "active_profiles": report["active_profiles"]}, indent=2))
        return 0
    if args.command == "quality":
        report = build_demo_platform()
        print(json.dumps(report["quality_after_erasure"], indent=2))
        return 0
    import uvicorn  # pragma: no cover
    from .service import create_app  # pragma: no cover
    uvicorn.run(create_app(), host=args.host, port=args.port)  # pragma: no cover
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
