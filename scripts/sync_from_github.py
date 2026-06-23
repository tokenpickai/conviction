#!/usr/bin/env python3
"""
Refresh local Serenity data from GitHub without calling X API.

GitHub Actions is the source of truth for fetched tweets and extracted data.
This script updates local data/ from origin/main, then rebuilds local derived
views so report generation can start from the latest committed dataset.
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(cmd, check=True):
    print("+ " + " ".join(cmd), flush=True)
    result = subprocess.run(cmd, cwd=ROOT, text=True)
    if check and result.returncode != 0:
        raise SystemExit(result.returncode)
    return result.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--branch", default="main")
    ap.add_argument(
        "--no-render",
        action="store_true",
        help="only sync data/; do not rebuild the local dashboard",
    )
    ap.add_argument(
        "--rebuild-queue",
        action="store_true",
        help="recompute report queue/decisions locally after syncing data/",
    )
    args = ap.parse_args()

    ref = f"{args.remote}/{args.branch}"
    run(["git", "fetch", args.remote, args.branch])
    run(["git", "restore", "--source", ref, "--worktree", "--", "data"])

    if args.no_render:
        return 0

    if args.rebuild_queue:
        run([sys.executable, "scripts/build_report_queue.py"])
        run([sys.executable, "scripts/build_report_decisions.py"])

    run([sys.executable, "scripts/build_site.py"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
