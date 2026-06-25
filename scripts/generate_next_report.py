#!/usr/bin/env python3
"""
Generate the next eligible flagship report from data/report_queue.json.

This is a safe wrapper around generate_ticker_report.py:
- select the top queued ticker unless --ticker is provided
- generate into a temporary draft path
- validate the draft before publishing to data/reports
- record failures in data/report_generation_failures.json
- rebuild the report queue after a successful publish
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    from profile_config import load_profile, profile_paths
except ImportError:  # pragma: no cover
    from scripts.profile_config import load_profile, profile_paths

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
QUEUE_PATH = DATA_DIR / "report_queue.json"
FAILURES_PATH = DATA_DIR / "report_generation_failures.json"
REPORTS_DIR = DATA_DIR / "reports"
GENERATOR = ROOT / "scripts" / "generate_ticker_report.py"
VALIDATOR = ROOT / "scripts" / "validate_reports.py"
QUEUE_BUILDER = ROOT / "scripts" / "build_report_queue.py"


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def load_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def load_dotenv(path=ROOT / ".env"):
    env = os.environ.copy()
    if not path.exists():
        return env
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in env:
            env[key] = value
    return env


def compact_queue_item(item):
    return {
        "ticker": item.get("ticker"),
        "company": item.get("company"),
        "status": item.get("status"),
        "priority": item.get("priority"),
        "report_score": item.get("report_score"),
        "total_mentions": item.get("total_mentions"),
        "unique_mention_days": item.get("unique_mention_days"),
        "last_mention": item.get("last_mention"),
        "why": item.get("why") or [],
    }


def queue_items(queue):
    return list(queue.get("next_reports") or [])


def select_item(queue, reports_dir=REPORTS_DIR, ticker=None, statuses=None, priorities=None):
    statuses = set(statuses or ["needs_report"])
    priorities = set(priorities or ["high", "medium"])
    ticker = ticker.upper() if ticker else None

    for item in queue_items(queue):
        item_ticker = (item.get("ticker") or "").upper()
        if not item_ticker:
            continue
        if ticker and item_ticker != ticker:
            continue
        if item.get("status") not in statuses:
            continue
        if item.get("priority") not in priorities:
            continue
        if item.get("has_report"):
            continue
        if (reports_dir / f"{item_ticker}.json").exists():
            continue
        return item
    return None


def run(cmd, stage, env=None):
    print(f"{stage}: {' '.join(cmd)}", flush=True)
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        env=env or os.environ.copy(),
        text=True,
        capture_output=True,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"{stage} failed with exit {result.returncode}")


def record_failure(path, ticker, stage, error, item, command=None):
    data = load_json(path, {"failures": []})
    failures = data.get("failures") or []
    failures.insert(0, {
        "failed_at": utc_now(),
        "ticker": ticker,
        "stage": stage,
        "error": str(error),
        "command": command or [],
        "queue_item": compact_queue_item(item),
    })
    data = {
        "generated_at": utc_now(),
        "failures": failures[:100],
    }
    save_json(path, data)


def clear_ticker_failures(path, ticker):
    data = load_json(path, None)
    if not data:
        return
    failures = [
        item for item in data.get("failures") or []
        if (item.get("ticker") or "").upper() != ticker.upper()
    ]
    if failures:
        save_json(path, {"generated_at": utc_now(), "failures": failures})
    elif path.exists():
        path.unlink()


def generator_cmd(args, ticker, out_path):
    cmd = [
        sys.executable,
        str(GENERATOR),
        ticker,
        "--mode", args.mode,
        "--max-items", str(args.max_items),
        "--text-limit", str(args.text_limit),
        "--max-tokens", str(args.max_tokens),
        "--timeout", str(args.timeout),
        "--out", str(out_path),
    ]
    if args.profile:
        cmd.extend(["--profile", args.profile])
    if args.model:
        cmd.extend(["--model", args.model])
    if args.generator_dry_run:
        cmd.append("--dry-run")
    return cmd


def publish_report(draft_path, final_path):
    final_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = final_path.with_suffix(".json.tmp")
    shutil.copyfile(draft_path, tmp)
    tmp.replace(final_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=None)
    ap.add_argument("--queue", default=str(QUEUE_PATH))
    ap.add_argument("--ticker", help="override queue order and generate this ticker if eligible")
    ap.add_argument("--statuses", default="needs_report", help="comma-separated statuses")
    ap.add_argument("--priorities", default="high,medium", help="comma-separated priorities")
    ap.add_argument("--mode", choices=["fast", "full"], default="fast")
    ap.add_argument("--model")
    ap.add_argument("--max-items", type=int, default=18)
    ap.add_argument("--text-limit", type=int, default=650)
    ap.add_argument("--max-tokens", type=int, default=6500)
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--failures", default=str(FAILURES_PATH))
    ap.add_argument("--dry-run", action="store_true", help="select and print the next ticker without generating")
    ap.add_argument("--generator-dry-run", action="store_true", help="call generator dry-run for prompt inspection")
    ap.add_argument("--no-rebuild-queue", action="store_true")
    args = ap.parse_args()
    if args.profile:
        paths = profile_paths(load_profile(args.profile))
        args.queue = str(paths["report_queue"])
        args.failures = str(paths["report_failures"])
        reports_dir = paths["reports_dir"]
    else:
        reports_dir = REPORTS_DIR

    queue = load_json(Path(args.queue), None)
    if not queue:
        print(f"ERROR: missing report queue: {args.queue}", file=sys.stderr)
        print("Run: python scripts/build_report_queue.py", file=sys.stderr)
        return 1

    statuses = [s.strip() for s in args.statuses.split(",") if s.strip()]
    priorities = [p.strip() for p in args.priorities.split(",") if p.strip()]
    item = select_item(queue, reports_dir=reports_dir, ticker=args.ticker, statuses=statuses, priorities=priorities)
    if not item:
        print("No eligible report queue item.")
        return 0

    ticker = item["ticker"].upper()
    print(
        f"Selected {ticker}: status={item.get('status')} priority={item.get('priority')} "
        f"score={item.get('report_score')} mentions={item.get('total_mentions')}"
    )
    for reason in item.get("why") or []:
        print(f"  - {reason}")

    if args.dry_run:
        return 0

    final_path = reports_dir / f"{ticker}.json"
    env = load_dotenv()
    with tempfile.TemporaryDirectory(prefix="serenity-report-") as tmp_dir:
        draft_path = Path(tmp_dir) / f"{ticker}.json"
        cmd = generator_cmd(args, ticker, draft_path)
        try:
            run(cmd, "Generate report", env=env)
            if args.generator_dry_run:
                print("Generator dry-run complete; no report was written.")
                return 0
            validate_cmd = [sys.executable, str(VALIDATOR), str(draft_path)]
            if args.profile:
                validate_cmd.extend(["--profile", args.profile])
            run(validate_cmd, "Validate draft")
            publish_report(draft_path, final_path)
            print(f"Published {final_path}")
            clear_ticker_failures(Path(args.failures), ticker)
            if not args.no_rebuild_queue:
                rebuild_cmd = [sys.executable, str(QUEUE_BUILDER)]
                if args.profile:
                    rebuild_cmd.extend(["--profile", args.profile])
                run(rebuild_cmd, "Rebuild report queue")
        except Exception as exc:
            record_failure(Path(args.failures), ticker, "generate_next_report", exc, item, command=cmd)
            print(f"ERROR: {exc}", file=sys.stderr)
            print(f"Recorded failure in {args.failures}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
