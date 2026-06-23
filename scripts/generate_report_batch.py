#!/usr/bin/env python3
"""
Generate flagship reports from the unified report decision layer.

This is the bridge from manual ticker selection to automated report production.
By default it reads data/report_decisions.json and processes only
write_new_thesis actions. Existing-report updates stay in the lightweight
hourly update lane handled by check_report_updates.py + apply_report_updates.py.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

try:
    from profile_config import load_profile, profile_paths
except ImportError:  # pragma: no cover
    from scripts.profile_config import load_profile, profile_paths

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
QUEUE_PATH = DATA_DIR / "report_queue.json"
DECISIONS_PATH = DATA_DIR / "report_decisions.json"
REPORTS_DIR = DATA_DIR / "reports"

GENERATOR = ROOT / "scripts" / "generate_ticker_report.py"
GENERATE_NEXT = ROOT / "scripts" / "generate_next_report.py"
CHECK_UPDATES = ROOT / "scripts" / "check_report_updates.py"
BUILD_QUEUE = ROOT / "scripts" / "build_report_queue.py"
BUILD_DECISIONS = ROOT / "scripts" / "build_report_decisions.py"
TRANSLATE_REASONS = ROOT / "scripts" / "translate_reason_snippets.py"
VALIDATOR = ROOT / "scripts" / "validate_reports.py"
AUDIT_REPORTS = ROOT / "scripts" / "audit_reports.py"
AUDIT_TRANSLATIONS = ROOT / "scripts" / "audit_reason_translations.py"
RENDER = ROOT / "scripts" / "serenity_render.py"


def load_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


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


def run(cmd, stage, env=None):
    print(f"{stage}: {' '.join(str(c) for c in cmd)}", flush=True)
    subprocess.run([str(c) for c in cmd], cwd=ROOT, env=env or os.environ.copy(), check=True)


def queue_items(queue):
    items = []
    items.extend(queue.get("updates_due") or [])
    items.extend(queue.get("next_reports") or [])
    return items


def decision_items(decisions):
    return list(decisions.get("automation_next") or [])


def select_queue_items(queue, limit, statuses, priorities, reports_dir=REPORTS_DIR, include_existing=False):
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
        if (reports_dir / f"{ticker}.json").exists() and not include_existing:
            continue
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected


def select_decision_items(decisions, limit, actions, priorities, reports_dir=REPORTS_DIR, include_existing=False):
    selected = []
    actions = set(actions)
    priorities = set(priorities)
    for item in decision_items(decisions):
        ticker = (item.get("ticker") or "").upper()
        if not ticker:
            continue
        if item.get("action") not in actions:
            continue
        if item.get("priority") not in priorities:
            continue
        if item.get("has_report") and not include_existing:
            continue
        if (reports_dir / f"{ticker}.json").exists() and not include_existing:
            continue
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected


def legacy_generator_cmd(item, args):
    ticker = item["ticker"]
    cmd = [
        sys.executable,
        GENERATOR,
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
        cmd.extend(["--out", str(Path(args.out_dir) / f"{ticker}.json")])
    if args.profile:
        cmd.extend(["--profile", args.profile])
    return cmd


def run_legacy_queue_item(item, args, env):
    cmd = legacy_generator_cmd(item, args)
    run(cmd, f"Generate {item['ticker']}", env=env)
    if args.validate:
        out_path = Path(args.out_dir) / f"{item['ticker']}.json" if args.out_dir else args.reports_dir / f"{item['ticker']}.json"
        run([sys.executable, VALIDATOR, out_path], f"Validate {item['ticker']}", env=env)


def run_decision_item(item, args, env):
    ticker = (item.get("ticker") or "").upper()
    action = item.get("action")
    if action != "write_new_thesis":
        print(f"Skipping {ticker}: action={action} is handled by update/regeneration workflows.")
        return False

    cmd = [
        sys.executable,
        GENERATE_NEXT,
        "--ticker",
        ticker,
        "--mode",
        args.mode,
        "--max-items",
        str(args.max_items),
        "--text-limit",
        str(args.text_limit),
        "--max-tokens",
        str(args.max_tokens),
        "--timeout",
        str(args.timeout),
        "--no-rebuild-queue",
    ]
    if args.profile:
        cmd.extend(["--profile", args.profile])
    if args.model:
        cmd.extend(["--model", args.model])
    run(cmd, f"Generate {ticker}", env=env)
    run(
        [sys.executable, TRANSLATE_REASONS, "--ticker", ticker, "--timeout", str(args.timeout)] + (["--profile", args.profile] if args.profile else []),
        f"Translate {ticker} reason snippets",
        env=env,
    )
    return True


def refresh_artifacts(env):
    profile_args = ["--profile", refresh_artifacts.profile] if refresh_artifacts.profile else []
    run([sys.executable, CHECK_UPDATES] + profile_args, "Check report update candidates", env=env)
    run([sys.executable, BUILD_QUEUE] + profile_args, "Build report queue", env=env)
    run([sys.executable, BUILD_DECISIONS] + profile_args, "Build report decisions", env=env)
    run([sys.executable, VALIDATOR] + profile_args, "Validate reports", env=env)
    run([sys.executable, AUDIT_REPORTS] + profile_args, "Audit reports", env=env)
    run([sys.executable, AUDIT_TRANSLATIONS] + profile_args, "Audit reason translations", env=env)
    run([sys.executable, RENDER] + profile_args, "Render dashboard", env=env)


refresh_artifacts.profile = None


def print_selected(items):
    for item in items:
        ticker = item.get("ticker")
        action = item.get("action") or item.get("status")
        print(
            f"{ticker}: action={action} priority={item.get('priority')} "
            f"score={item.get('report_score')} mentions={item.get('total_mentions')}"
        )
        for reason in (item.get("why") or [])[:5]:
            print(f"  - {reason}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=None)
    ap.add_argument("--source", choices=["decisions", "queue"], default="decisions")
    ap.add_argument("--decisions", default=str(DECISIONS_PATH))
    ap.add_argument("--queue", default=str(QUEUE_PATH))
    ap.add_argument("--limit", type=int, default=1)
    ap.add_argument("--actions", default="write_new_thesis", help="comma-separated decision actions")
    ap.add_argument("--statuses", default="needs_report", help="comma-separated queue statuses")
    ap.add_argument("--priorities", default="high,medium", help="comma-separated priorities")
    ap.add_argument("--include-existing", action="store_true")
    ap.add_argument("--mode", choices=["fast", "full"], default="fast")
    ap.add_argument("--model")
    ap.add_argument("--max-items", type=int, default=18)
    ap.add_argument("--text-limit", type=int, default=650)
    ap.add_argument("--max-tokens", type=int, default=6500)
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--out-dir", help="legacy queue mode only: write reports outside data/reports")
    ap.add_argument("--no-validate", action="store_true", help="legacy queue mode only: skip report validation")
    ap.add_argument("--no-refresh", action="store_true", help="skip queue/decision/render refresh after generation")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    args.validate = not args.no_validate
    if args.profile:
        paths = profile_paths(load_profile(args.profile))
        args.decisions = str(paths["report_decisions"])
        args.queue = str(paths["report_queue"])
        args.reports_dir = paths["reports_dir"]
    else:
        args.reports_dir = REPORTS_DIR
    refresh_artifacts.profile = args.profile

    priorities = [p.strip() for p in args.priorities.split(",") if p.strip()]
    if args.source == "decisions":
        decisions = load_json(Path(args.decisions), None)
        if not decisions:
            print(f"ERROR: missing report decisions: {args.decisions}", file=sys.stderr)
            print(
                "Run: python scripts/check_report_updates.py && "
                "python scripts/build_report_queue.py && "
                "python scripts/build_report_decisions.py",
                file=sys.stderr,
            )
            return 1
        actions = [a.strip() for a in args.actions.split(",") if a.strip()]
        selected = select_decision_items(decisions, args.limit, actions, priorities, args.reports_dir, args.include_existing)
    else:
        queue = load_json(Path(args.queue), None)
        if not queue:
            print(f"ERROR: missing report queue: {args.queue}", file=sys.stderr)
            print("Run: python scripts/build_report_queue.py", file=sys.stderr)
            return 1
        statuses = [s.strip() for s in args.statuses.split(",") if s.strip()]
        selected = select_queue_items(queue, args.limit, statuses, priorities, args.reports_dir, args.include_existing)

    if not selected:
        print("No eligible report items.")
        return 0

    print_selected(selected)
    if args.dry_run:
        print("\nDry run only. Re-run without --dry-run to generate.")
        return 0

    env = load_dotenv()
    generated = 0
    for item in selected:
        if args.source == "decisions":
            generated += 1 if run_decision_item(item, args, env) else 0
        else:
            run_legacy_queue_item(item, args, env)
            generated += 1

    if generated and args.source == "decisions" and not args.no_refresh:
        refresh_artifacts(env)

    print(f"Generated {generated} report(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
