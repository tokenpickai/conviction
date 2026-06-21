#!/usr/bin/env python3
"""
Audit ticker detail reason panels for untranslated English snippets.

The long thesis reports are already written in Chinese, but the compact
看多理由 / 提到的風險 panels come from extracted mention reasons. This script
checks published-report tickers and flags raw English reason snippets that do
not have a `zhReasonText` mapping in the static renderer.
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import serenity_render  # noqa: E402


RENDERER = ROOT / "scripts" / "serenity_render.py"
ASCII_WORD_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9+\-/]{2,}\b")
SINGLE_KEY_RE = re.compile(r"^\s*'((?:\\'|[^'])*)'\s*:", re.MULTILINE)
DOUBLE_KEY_RE = re.compile(r'^\s*"((?:\\"|[^"])*)"\s*:', re.MULTILINE)

JARGON_ALLOW = {
    "AI", "ASIC", "ATM", "BOM", "BTC", "CPO", "CW", "DC", "EML", "GPU",
    "H100", "InP", "LLM", "NVDA", "OCS", "TPU", "YTD",
}


def load_translation_keys():
    text = RENDERER.read_text(encoding="utf-8")
    keys = set()
    for raw in SINGLE_KEY_RE.findall(text):
        keys.add(raw.replace("\\'", "'"))
    for raw in DOUBLE_KEY_RE.findall(text):
        keys.add(raw.replace('\\"', '"'))
    return keys


def englishy(text):
    words = ASCII_WORD_RE.findall(text or "")
    prose_words = [
        w for w in words
        if w.upper() not in JARGON_ALLOW
        and not re.fullmatch(r"[A-Z]{1,5}", w)
        and not re.fullmatch(r"\d+[A-Za-z]*", w)
    ]
    return len(prose_words) >= 3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", help="audit one ticker only")
    ap.add_argument("--max", type=int, default=80, help="maximum findings to print")
    args = ap.parse_args()

    translations = load_translation_keys()
    dd = serenity_render.dd_data()
    tickers = sorted(serenity_render.REPORTS)
    if args.ticker:
        tickers = [args.ticker.upper()]

    findings = []
    for ticker in tickers:
        item = dd.get(ticker) or {}
        for panel in ("reasonsBull", "reasonsRisk"):
            for reason, url, date in item.get(panel) or []:
                if reason in translations:
                    continue
                if englishy(reason):
                    findings.append({
                        "ticker": ticker,
                        "panel": panel,
                        "date": date,
                        "reason": reason,
                        "url": url,
                    })

    if findings:
        print(f"FAIL: {len(findings)} untranslated reason snippets.")
        for finding in findings[: args.max]:
            print(
                f"{finding['ticker']} {finding['panel']} {finding['date']}: "
                f"{finding['reason']}"
            )
        if len(findings) > args.max:
            print(f"... {len(findings) - args.max} more")
        return 1

    print(f"PASS: reason panels translated for {len(tickers)} report tickers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
