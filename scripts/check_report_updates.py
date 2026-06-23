#!/usr/bin/env python3
"""
Detect whether new Serenity posts deserve a thesis report update.

This script is intentionally conservative. It does not rewrite polished reports by
default; it classifies post deltas so a later AI writer can turn high-signal
candidates into `updates` entries.
"""

import argparse
import json
from pathlib import Path

try:
    from profile_config import load_profile, profile_paths
except ImportError:  # pragma: no cover
    from scripts.profile_config import load_profile, profile_paths

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
STOCKS_DIR = DATA_DIR / "db" / "stocks"
REPORTS_DIR = DATA_DIR / "reports"
DEFAULT_OUT = DATA_DIR / "report_update_candidates.json"

HIGH_SIGNAL_TERMS = {
    "favorite": 8,
    "favourite": 8,
    "highest conviction": 10,
    "conviction": 7,
    "own": 7,
    "owns": 7,
    "holding": 6,
    "long": 8,
    "sold": 10,
    "sell": 10,
    "not hold": 10,
    "would not hold": 12,
    "red flag": 12,
    "dilution": 12,
    "offering": 8,
    "secondary": 8,
    "bearish": 10,
    "risk": 7,
    "short seller": 8,
    "lawsuit": 8,
    "export control": 8,
    "ban": 6,
    "sanction": 7,
    "thesis": 8,
    "played out": 8,
    "validation": 8,
    "confirmed": 7,
    "channel check": 7,
    "purchase agreement": 8,
    "capacity": 5,
    "allocation": 7,
    "bottleneck": 8,
    "chokepoint": 8,
    "ramp": 5,
    "revenue ramp": 7,
    "margin": 4,
    "pricing": 5,
    "hyperscaler": 5,
    "amd": 5,
    "nvidia": 5,
    "nvda": 5,
    "amazon": 5,
    "amzn": 5,
    "microsoft": 5,
    "msft": 5,
    "jabil": 5,
    "jbl": 5,
    "globalfoundries": 5,
    "gfs": 5,
}

LOW_SIGNAL_TYPES = {"watchlist", "list", "comparison", "background"}
REGRESSION_STANCES = {"bearish", "mixed", "more_cautious", "less_bullish"}


def load_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def report_cutoff(report):
    if report.get("coverage_through"):
        return report["coverage_through"]

    dates = []
    for item in report.get("source_posts_used") or []:
        if item.get("date"):
            dates.append(item["date"])
    for item in report.get("updates") or []:
        if item.get("date"):
            dates.append(item["date"])
    return max(dates) if dates else ""


def report_stance(report):
    updates = report.get("updates") or []
    if updates:
        return (updates[0].get("stance") or "").lower()
    text = json.dumps(report, ensure_ascii=False).lower()
    if "看空" in text or "bearish" in text:
        return "bearish"
    if "看多" in text or "bullish" in text:
        return "bullish"
    return "unknown"


def unique_mentions_after(stock, cutoff):
    by_id = {}
    for mention in stock.get("mentions") or []:
        date = mention.get("date") or ""
        tweet_id = mention.get("tweet_id")
        if not tweet_id or date <= cutoff:
            continue
        prev = by_id.get(tweet_id)
        if prev is None or mention_score(mention) > mention_score(prev):
            by_id[tweet_id] = mention
    return sorted(by_id.values(), key=lambda m: ((m.get("date") or ""), (m.get("tweet_id") or "")))


def term_hits(text):
    lower = text.lower()
    hits = []
    score = 0
    for term, weight in HIGH_SIGNAL_TERMS.items():
        if term in lower:
            hits.append(term)
            score += weight
    return score, sorted(hits)


def mention_score(mention):
    score = 0
    mention_type = mention.get("mention_type") or ""
    stance = (mention.get("stance") or "").lower()
    text = mention.get("text") or ""
    reasons = " ".join(mention.get("reasons") or [])
    combined = f"{text}\n{reasons}"

    if mention_type == "explicit_stance":
        score += 18
    elif mention_type in LOW_SIGNAL_TYPES:
        score -= 8

    if stance in {"bullish", "bearish"}:
        score += 12
    elif stance in {"mixed", "neutral"}:
        score += 4

    if mention.get("is_risk"):
        score += 14

    conviction = mention.get("conviction")
    if conviction == "high":
        score += 12
    elif conviction == "medium":
        score += 6

    reasons_count = len(mention.get("reasons") or [])
    score += min(12, reasons_count * 3)

    term_score, _ = term_hits(combined)
    score += term_score

    engagement = mention.get("engagement") or {}
    views = int(engagement.get("views") or 0)
    likes = int(engagement.get("likes") or 0)
    score += min(8, views // 25000)
    score += min(6, likes // 100)

    return score


def classify_candidate(ticker, report, mentions):
    if not mentions:
        return None

    current_stance = report_stance(report)
    scored = []
    all_hits = set()
    stance_shift = False
    risk_posts = 0
    explicit_posts = 0

    for mention in mentions:
        score = mention_score(mention)
        text = mention.get("text") or ""
        reasons = " ".join(mention.get("reasons") or [])
        _, hits = term_hits(f"{text}\n{reasons}")
        all_hits.update(hits)
        stance = (mention.get("stance") or "").lower()
        if mention.get("is_risk"):
            risk_posts += 1
        if mention.get("mention_type") == "explicit_stance":
            explicit_posts += 1
        if current_stance in {"bullish", "still_bullish"} and stance in REGRESSION_STANCES:
            stance_shift = True
            score += 22
        if current_stance == "bearish" and stance == "bullish":
            stance_shift = True
            score += 18
        scored.append((score, mention, hits))

    scored.sort(key=lambda item: item[0], reverse=True)
    top_score = scored[0][0]

    if stance_shift and top_score >= 35:
        classification = "regeneration_candidate" if len(mentions) >= 5 else "update_candidate"
        importance = "high"
        reason = f"{ticker} has a likely stance shift after the report coverage date."
    elif top_score >= 50 or (risk_posts and top_score >= 42):
        classification = "update_candidate"
        importance = "high" if top_score >= 62 else "medium"
        reason = f"{ticker} has new high-signal thesis evidence."
    elif explicit_posts >= 3 and top_score >= 34:
        classification = "update_candidate"
        importance = "medium"
        reason = f"{ticker} has several new explicit Serenity views worth reviewing."
    else:
        classification = "ignore"
        importance = "low"
        reason = f"{ticker} has new mentions, but they look like low-signal or repetitive context."

    return {
        "ticker": ticker,
        "classification": classification,
        "importance": importance,
        "reason": reason,
        "top_score": top_score,
        "current_report_stance": current_stance,
        "new_posts": len(mentions),
        "signal_terms": sorted(all_hits),
        "source_tweet_ids": [m.get("tweet_id") for _, m, _ in scored[:8] if m.get("tweet_id")],
        "posts": [
            {
                "tweet_id": mention.get("tweet_id"),
                "date": mention.get("date"),
                "url": mention.get("url"),
                "stance": mention.get("stance"),
                "mention_type": mention.get("mention_type"),
                "is_risk": bool(mention.get("is_risk")),
                "conviction": mention.get("conviction"),
                "score": score,
                "reasons": (mention.get("reasons") or [])[:5],
                "text_preview": compact(mention.get("text") or "", 260),
            }
            for score, mention, _ in scored[:10]
        ],
    }


def compact(text, limit):
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def build_output(reports_dir, stocks_dir, since=None, manifest_path=DATA_DIR / "db" / "manifest.json"):
    manifest = load_json(manifest_path, {})
    candidates = []
    checked = 0

    for report_path in sorted(reports_dir.glob("*.json")):
        report = load_json(report_path, {})
        ticker = (report.get("ticker") or report_path.stem).upper()
        stock = load_json(stocks_dir / f"{ticker}.json", None)
        if not stock:
            continue

        cutoff = since or report_cutoff(report)
        mentions = unique_mentions_after(stock, cutoff)
        checked += 1
        candidate = classify_candidate(ticker, report, mentions)
        if candidate:
            candidate["cutoff_date"] = cutoff
            candidate["coverage_through"] = report.get("coverage_through") or None
            candidates.append(candidate)

    priority = {"regeneration_candidate": 0, "update_candidate": 1, "ignore": 2}
    candidates.sort(key=lambda item: (priority.get(item["classification"], 9), item["ticker"]))
    return {
        "data_generated_at": manifest.get("generated_at"),
        "reports_checked": checked,
        "reports_with_new_posts": len(candidates),
        "actionable": sum(1 for c in candidates if c["classification"] != "ignore"),
        "candidates": candidates,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=None)
    ap.add_argument("--reports", default=str(REPORTS_DIR))
    ap.add_argument("--stocks", default=str(STOCKS_DIR))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--since", help="override report coverage cutoff, YYYY-MM-DD")
    ap.add_argument("--print", action="store_true", help="print JSON instead of writing it")
    args = ap.parse_args()
    if args.profile:
        paths = profile_paths(load_profile(args.profile))
        args.reports = str(paths["reports_dir"])
        args.stocks = str(paths["stocks_dir"])
        args.out = str(paths["report_update_candidates"])
        manifest_path = paths["manifest"]
    else:
        manifest_path = DATA_DIR / "db" / "manifest.json"

    output = build_output(Path(args.reports), Path(args.stocks), since=args.since, manifest_path=manifest_path)
    if args.print:
        print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        save_json(Path(args.out), output)
        print(
            f"Checked {output['reports_checked']} reports; "
            f"{output['actionable']} actionable update candidates."
        )


if __name__ == "__main__":
    main()
