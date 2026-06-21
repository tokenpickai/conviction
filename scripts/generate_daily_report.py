#!/usr/bin/env python3
"""
Choose and optionally generate the next report from a topic cluster.

This is the automation bridge between `report_decisions.json` and the guarded
single-report generator. By default it previews the next ticker without spending
API credits. Use `--execute` to actually generate one report and run all gates.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DECISIONS_PATH = DATA_DIR / "report_decisions.json"
STOCKS_DIR = DATA_DIR / "db" / "stocks"
REPORTS_DIR = DATA_DIR / "reports"

GENERATE_NEXT = ROOT / "scripts" / "generate_next_report.py"
CHECK_UPDATES = ROOT / "scripts" / "check_report_updates.py"
BUILD_QUEUE = ROOT / "scripts" / "build_report_queue.py"
BUILD_DECISIONS = ROOT / "scripts" / "build_report_decisions.py"
RENDER = ROOT / "scripts" / "serenity_render.py"
VALIDATE = ROOT / "scripts" / "validate_reports.py"
AUDIT_TRANSLATIONS = ROOT / "scripts" / "audit_reason_translations.py"
TRANSLATE_REASONS = ROOT / "scripts" / "translate_reason_snippets.py"
SMOKE = ROOT / "scripts" / "smoke_report_render.py"

CLUSTERS = {
    "photonics": {
        "label": "Photonics / CPO",
        "tickers": {
            "AAOI", "ALAB", "AMKR", "ASX", "AXTI", "COHR", "CRDO", "FN", "GLW",
            "IQE", "JBL", "LITE", "MRVL", "MTSI", "POET", "SIVE", "SOI", "TSEM",
            "VIAV",
        },
        "terms": (
            "cpo", "photonic", "photonics", "optical", "laser", "transceiver",
            "interconnect", "inp", "silicon photonics", "coherent", "lumentum",
            "jabil", "cred0", "credo", "marvell", "soitec", "iqe",
        ),
        "prefer": ("TSEM", "JBL", "FN", "AMKR", "ASX", "IQE", "SOI", "CRDO", "MRVL", "ALAB"),
        "exclude": {"AMZN", "GOOGL", "META", "MSFT", "NVDA", "ORCL"},
    },
    "neocloud": {
        "label": "Neocloud / AI infrastructure",
        "tickers": {"NBIS", "IREN", "CRWV", "CIFR", "WULF", "CORZ", "APLD", "HUT", "RIOT"},
        "terms": ("neocloud", "ai cloud", "gpu cloud", "data center", "datacenter", "bitcoin miner"),
        "prefer": ("WULF", "APLD", "HUT", "CORZ", "RIOT"),
        "exclude": set(),
    },
    "memory": {
        "label": "Memory / HBM",
        "tickers": {"MU", "SNDK", "WDC", "SKM", "TSM", "SAMSUNG"},
        "terms": ("memory", "hbm", "dram", "nand", "sk hynix", "micron", "sandisk"),
        "prefer": ("MU", "SNDK", "WDC", "SKM"),
        "exclude": set(),
    },
}


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


def compact(text, limit=180):
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def stock_meta(ticker):
    path = STOCKS_DIR / f"{ticker}.json"
    return load_json(path, {})


def haystack(item, stock):
    evidence_text = " ".join(e.get("text_preview") or "" for e in item.get("evidence") or [])
    return " ".join([
        item.get("ticker") or "",
        item.get("company") or "",
        stock.get("company") or "",
        stock.get("industry") or "",
        " ".join(item.get("signal_terms") or []),
        " ".join(item.get("why") or []),
        evidence_text,
    ]).lower()


def cluster_match(item, cluster):
    ticker = (item.get("ticker") or "").upper()
    stock = stock_meta(ticker)
    cfg = CLUSTERS[cluster]
    if ticker in cfg["exclude"]:
        return False, "excluded broad platform"
    if ticker in cfg["tickers"]:
        return True, "ticker allowlist"
    focused = " ".join([
        ticker,
        item.get("company") or "",
        stock.get("company") or "",
        stock.get("industry") or "",
    ]).lower()
    if any(term in focused for term in cfg["terms"]):
        return True, "company/industry match"
    return False, ""


def preference_rank(ticker, cluster):
    pref = CLUSTERS[cluster].get("prefer") or ()
    try:
        return pref.index(ticker)
    except ValueError:
        return len(pref) + 100


def explain_item(item, cluster, reason):
    ticker = item.get("ticker")
    stock = stock_meta(ticker)
    return {
        "ticker": ticker,
        "company": item.get("company") or stock.get("company"),
        "cluster": CLUSTERS[cluster]["label"],
        "match_reason": reason,
        "priority": item.get("priority"),
        "report_score": item.get("report_score"),
        "total_mentions": item.get("total_mentions"),
        "unique_mention_days": item.get("unique_mention_days"),
        "last_mention": item.get("last_mention"),
        "industry": stock.get("industry"),
        "why": item.get("why") or [],
        "evidence": [
            {
                "date": e.get("date"),
                "stance": e.get("stance"),
                "score": e.get("score"),
                "preview": compact(e.get("text_preview"), 220),
            }
            for e in (item.get("evidence") or [])[:3]
        ],
    }


def select_candidates(decisions, cluster, limit, ticker=None):
    selected = []
    all_items = decisions.get("decisions") or decisions.get("automation_next") or []
    for item in all_items:
        item_ticker = (item.get("ticker") or "").upper()
        if not item_ticker:
            continue
        if ticker and item_ticker != ticker.upper():
            continue
        if item.get("action") != "write_new_thesis":
            continue
        if item.get("has_report") or (REPORTS_DIR / f"{item_ticker}.json").exists():
            continue
        ok, reason = cluster_match(item, cluster)
        if not ok:
            continue
        selected.append((item, reason))

    selected.sort(
        key=lambda pair: (
            preference_rank((pair[0].get("ticker") or "").upper(), cluster),
            -(pair[0].get("report_score") or 0),
            pair[0].get("ticker") or "",
        )
    )
    return selected[:limit]


def run(cmd, stage, env=None):
    print(f"{stage}: {' '.join(str(c) for c in cmd)}", flush=True)
    result = subprocess.run(
        [str(c) for c in cmd],
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


def refresh_and_gate(env, smoke):
    run([sys.executable, CHECK_UPDATES], "Check report updates", env=env)
    run([sys.executable, BUILD_QUEUE], "Build report queue", env=env)
    run([sys.executable, BUILD_DECISIONS], "Build report decisions", env=env)
    run([sys.executable, VALIDATE], "Validate reports", env=env)
    run([sys.executable, RENDER], "Render dashboard", env=env)
    run([sys.executable, AUDIT_TRANSLATIONS], "Audit reason translations", env=env)
    if smoke:
        run([sys.executable, SMOKE], "Browser smoke reports", env=env)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cluster", choices=sorted(CLUSTERS), default="photonics")
    ap.add_argument("--limit", type=int, default=1)
    ap.add_argument("--ticker", help="force a ticker, still checked against cluster unless --any-cluster is used")
    ap.add_argument("--any-cluster", action="store_true", help="allow --ticker outside the cluster")
    ap.add_argument("--execute", action="store_true", help="generate reports instead of previewing selection")
    ap.add_argument("--mode", choices=["fast", "full"], default="fast")
    ap.add_argument("--model")
    ap.add_argument("--max-items", type=int, default=18)
    ap.add_argument("--text-limit", type=int, default=650)
    ap.add_argument("--max-tokens", type=int, default=6500)
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--no-smoke", action="store_true", help="skip browser smoke after generation")
    args = ap.parse_args()

    decisions = load_json(DECISIONS_PATH, {})
    if args.ticker and args.any_cluster:
        decisions = {
            "decisions": [
                item for item in (decisions.get("decisions") or decisions.get("automation_next") or [])
                if (item.get("ticker") or "").upper() == args.ticker.upper()
            ]
        }
        selected = [(item, "forced ticker") for item in decisions["decisions"]]
    else:
        selected = select_candidates(decisions, args.cluster, args.limit, ticker=args.ticker)

    if not selected:
        print(f"No eligible {CLUSTERS[args.cluster]['label']} report candidate.")
        return 0

    print(f"Selected {len(selected)} {CLUSTERS[args.cluster]['label']} candidate(s):")
    for item, reason in selected:
        info = explain_item(item, args.cluster, reason)
        print(json.dumps(info, ensure_ascii=False, indent=2))

    if not args.execute:
        print("\nPreview only. Re-run with --execute to generate.")
        return 0

    env = load_dotenv()
    generated = []
    for item, _reason in selected:
        ticker = (item.get("ticker") or "").upper()
        cmd = [
            sys.executable,
            GENERATE_NEXT,
            "--ticker", ticker,
            "--mode", args.mode,
            "--max-items", str(args.max_items),
            "--text-limit", str(args.text_limit),
            "--max-tokens", str(args.max_tokens),
            "--timeout", str(args.timeout),
            "--no-rebuild-queue",
        ]
        if args.model:
            cmd.extend(["--model", args.model])
        run(cmd, f"Generate {ticker}", env=env)
        run(
            [sys.executable, TRANSLATE_REASONS, "--ticker", ticker, "--timeout", str(args.timeout)],
            f"Translate {ticker} reason snippets",
            env=env,
        )
        generated.append(ticker)

    refresh_and_gate(env, smoke=not args.no_smoke)
    print("Generated reports: " + ", ".join(generated))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
