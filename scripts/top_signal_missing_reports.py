#!/usr/bin/env python3
"""
List high Serenity-signal tickers that do not have published memos yet.

This is intentionally a dry-run utility: it reuses the same signal score used
by the dashboard Top 3, but it does not call an LLM or generate reports.
"""

import argparse
import os
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from profile_config import arg_value  # noqa: E402

_PROFILE_ARG = arg_value(sys.argv, "--profile")
if _PROFILE_ARG:
    os.environ["CONVICTION_PROFILE"] = _PROFILE_ARG

_argv = sys.argv[:]
try:
    sys.argv = [sys.argv[0]] + (["--profile", _PROFILE_ARG] if _PROFILE_ARG else [])
    import serenity_render as sr  # noqa: E402
finally:
    sys.argv = _argv


def missing_signal_items(limit):
    items = []
    for ticker in sr.mdates:
        if ticker in sr.REPORTS:
            continue
        item = sr._serenity_signal_score(ticker)
        if item:
            item["company"] = sr.co_of(ticker)
            item["market"] = sr.market_of(ticker)
            item["theme"] = sr.theme_of(ticker)
            items.append(item)
    items.sort(key=lambda x: (x["score"], x["w28"], x["mentions"], x["bull"]), reverse=True)
    return items[:limit]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=None)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = ap.parse_args()

    items = missing_signal_items(args.limit)
    if args.json:
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return 0

    if not items:
        print("No high-signal tickers are missing memos.")
        return 0

    print("Top Serenity signals missing memos:")
    for i, item in enumerate(items, 1):
        reasons = " · ".join(item.get("reasons") or [])
        label = f"{item['ticker']} ({item['market']}, {item['theme']})"
        print(f"{i}. {label} score {item['score']} — {item['company']}")
        print(f"   {reasons}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
