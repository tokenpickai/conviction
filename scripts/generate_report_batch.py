#!/usr/bin/env python3
"""
Generate reports from data/report_queue.json in priority order.

This is the bridge from manual ticker selection to automated report production.
It intentionally processes a small batch by default so quality can be inspected
before scaling up.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
QUEUE_PATH = DATA_DIR / "report_queue.json"
REPORTS_DIR = DATA_DIR / "reports"
GENERATOR = ROOT / "scripts" / "generate_ticker_report.py"
VALIDATOR = ROOT / "scripts" / "validate_reports.py"


def load_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def queue_items(queue):
    items = []
    items.extend(queue.get("updates_due") or [])
    items.extend(queue.get("next_reports") or [])
    return items


def select_items(queue, limit, statuses, priorities, include_existing=False):
    selected = []
    statuses = set(statuses)
    priorities = set(priorities)
    for item in queue_items(queue):
        ticker = (item.get("ticker") or "").upper()
        if not ticker:
            continue
        if item.get("status") not in statuses:
            continue
        if item.get("priority") not in priorities:
            continue
        if item.get("has_report") and not include_existing:
            continue
        if (REPORTS_DIR / f"{ticker}.json").exists() and not include_existing:
            continue
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected


def run_generator(item, args):
    ticker = item["ticker"]
    out_path = None
    cmd = [
        sys.executable,
        str(GENERATOR),
        ticker,
        "--mode", args.mode,
        "--max-items", str(args.max_items),
        "--text-limit", str(args.text_limit),
        "--max-tokens", str(args.max_tokens),
        "--timeout", str(args.timeout),
    ]
    if args.model:
        cmd.extend(["--model", args.model])
    if args.out_dir:
        out_path = Path(args.out_dir) / f"{ticker}.json"
        cmd.extend(["--out", str(out_path)])
    else:
        out_path = REPORTS_DIR / f"{ticker}.json"

    print(f"Generating {ticker}: {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, cwd=ROOT, env=os.environ.copy(), check=True)
    if args.validate:
        print(f"Validating {out_path}", flush=True)
        subprocess.run([sys.executable, str(VALIDATOR), str(out_path)], cwd=ROOT, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", default=str(QUEUE_PATH))
    ap.add_argument("--limit", type=int, default=1)
    ap.add_argument("--statuses", default="needs_report", help="comma-separated queue statuses")
    ap.add_argument("--priorities", default="high,medium", help="comma-separated priorities")
    ap.add_argument("--include-existing", action="store_true")
    ap.add_argument("--mode", choices=["fast", "full"], default="fast")
    ap.add_argument("--model")
    ap.add_argument("--max-items", type=int, default=18)
    ap.add_argument("--text-limit", type=int, default=650)
    ap.add_argument("--max-tokens", type=int, default=6500)
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--out-dir", help="write reports to a separate directory instead of data/reports")
    ap.add_argument("--no-validate", action="store_true", help="skip report validation after generation")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    args.validate = not args.no_validate

    queue = load_json(Path(args.queue), None)
    if not queue:
        print(f"ERROR: missing report queue: {args.queue}", file=sys.stderr)
        print("Run: python scripts/build_report_queue.py", file=sys.stderr)
        sys.exit(1)

    statuses = [s.strip() for s in args.statuses.split(",") if s.strip()]
    priorities = [s.strip() for s in args.priorities.split(",") if s.strip()]
    selected = select_items(queue, args.limit, statuses, priorities, include_existing=args.include_existing)

    if not selected:
        print("No eligible report queue items.")
        return

    for item in selected:
        ticker = item["ticker"]
        print(
            f"{ticker}: status={item.get('status')} priority={item.get('priority')} "
            f"score={item.get('report_score')} mentions={item.get('total_mentions')}"
        )
        if args.dry_run:
            continue
        run_generator(item, args)


if __name__ == "__main__":
    main()
