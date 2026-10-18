"""One-time, read-only import of legacy dashboard JSONL runs into PostgreSQL."""

import argparse
import json
from pathlib import Path
import sys

from db import engine
from services.dashboard_runs import DashboardRunManager


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        default=Path("resultados/dashboard_runs"),
        help="legacy run folder; files are read but never changed",
    )
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parent.parent
    manager = DashboardRunManager(
        None, None, engine, repo_root, recover_interrupted=False,
    )
    try:
        report = manager.import_legacy_runs(args.source)
    finally:
        manager.shutdown()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
