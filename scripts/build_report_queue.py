#!/usr/bin/env python3
"""
Build a prioritized queue of tickers that deserve Serenity thesis reports.

The queue is deterministic and cheap to run. It uses the extracted local stock
database rather than calling an LLM, so it can run during hourly sync.
"""

import argparse
import json
from collections import Counter
from pathlib import Path

try:
    from check_report_updates import HIGH_SIGNAL_TERMS, mention_score, term_hits
except ImportError:  # pragma: no cover - useful when imported from repo root
    from scripts.check_report_updates import HIGH_SIGNAL_TERMS, mention_score, term_hits

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
STOCKS_DIR = DATA_DIR / "db" / "stocks"
REPORTS_DIR = DATA_DIR / "reports"
DEFAULT_OUT = DATA_DIR / "report_queue.json"
UPDATE_CANDIDATES = DATA_DIR / "report_update_candidates.json"

LOW_SIGNAL_TYPES = {"watchlist", "list", "comparison", "background"}


def load_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def unique_mentions(stock):
    by_id = {}
    for mention in stock.get("mentions") or []:
        tweet_id = mention.get("tweet_id")
        if not tweet_id:
            continue
        prev = by_id.get(tweet_id)
        if prev is None or mention_score(mention) > mention_score(prev):
            by_id[tweet_id] = mention
    return sorted(by_id.values(), key=lambda m: ((m.get("date") or ""), (m.get("tweet_id") or "")))


def compact(text, limit=220):
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def report_files(reports_dir):
    return {p.stem.upper(): p for p in reports_dir.glob("*.json")}


def update_status_map(path):
    data = load_json(path, {})
    out = {}
    for item in data.get("candidates") or []:
        ticker = (item.get("ticker") or "").upper()
        classification = item.get("classification")
        if ticker and classification and classification != "ignore":
            out[ticker] = classification
    return out


def score_stock(stock):
    mentions = unique_mentions(stock)
    if not mentions:
        return None

    mention_scores = sorted((mention_score(m) for m in mentions), reverse=True)
    top_scores = mention_scores[:30]
    dates = {m.get("date") for m in mentions if m.get("date")}
    explicit = [m for m in mentions if m.get("mention_type") == "explicit_stance"]
    substantive = [
        m for m in mentions
        if m.get("mention_type") == "explicit_stance"
        or m.get("is_risk")
        or m.get("reasons")
        or mention_score(m) >= 28
    ]
    risks = [m for m in mentions if m.get("is_risk")]
    high_conviction = [m for m in mentions if m.get("conviction") == "high"]
    medium_conviction = [m for m in mentions if m.get("conviction") == "medium"]
    stances = Counter((m.get("stance") or "unknown") for m in mentions)
    mention_types = Counter((m.get("mention_type") or "unknown") for m in mentions)

    combined_text = "\n".join(
        f"{m.get('text') or ''}\n{' '.join(m.get('reasons') or [])}"
        for m in mentions
    )
    term_score, hits = term_hits(combined_text)
    term_bonus = min(90, term_score // 3)

    score = 0
    score += sum(top_scores[:12])
    score += sum(top_scores[12:30]) // 2
    score += min(70, len(mentions) * 2)
    score += min(80, len(dates) * 7)
    score += min(90, len(explicit) * 9)
    score += min(70, len(substantive) * 5)
    score += min(60, len(high_conviction) * 14)
    score += min(36, len(medium_conviction) * 6)
    score += min(50, len(risks) * 10)
    score += term_bonus

    if len(mentions) >= 30:
        score += 35
    elif len(mentions) >= 12:
        score += 20
    elif len(mentions) >= 5:
        score += 10

    if len(dates) >= 10:
        score += 35
    elif len(dates) >= 4:
        score += 18

    if not substantive and mention_types.get("list", 0) + mention_types.get("background", 0) >= len(mentions) * 0.7:
        score -= 80

    top_mentions = sorted(mentions, key=mention_score, reverse=True)[:6]
    reasons = build_reasons(stock, mentions, explicit, substantive, risks, high_conviction, hits)

    return {
        "score": int(score),
        "mentions": mentions,
        "unique_days": len(dates),
        "explicit_count": len(explicit),
        "substantive_count": len(substantive),
        "risk_count": len(risks),
        "high_conviction_count": len(high_conviction),
        "stance_counts": dict(sorted(stances.items())),
        "signal_terms": hits[:18],
        "reasons": reasons,
        "evidence": top_mentions,
    }


def build_reasons(stock, mentions, explicit, substantive, risks, high_conviction, hits):
    reasons = []
    total = len(mentions)
    days = len({m.get("date") for m in mentions if m.get("date")})
    if total:
        reasons.append(f"{total} total mentions across {days} days")
    if explicit:
        reasons.append(f"{len(explicit)} explicit stance posts")
    if substantive:
        reasons.append(f"{len(substantive)} substantive thesis-like posts")
    if high_conviction:
        reasons.append(f"{len(high_conviction)} high-conviction mentions")
    if risks:
        reasons.append(f"{len(risks)} risk/caution posts")
    if hits:
        reasons.append("high-signal terms: " + ", ".join(hits[:6]))
    if stock.get("last_mention"):
        reasons.append(f"latest mention {stock.get('last_mention')}")
    return reasons[:7]


def classify_report_need(metrics, has_report, update_status=None):
    if update_status == "regeneration_candidate":
        return "needs_regeneration", "high"
    if update_status == "update_candidate":
        return "needs_update", "high"
    if has_report:
        return "has_report", "none"

    score = metrics["score"]
    substantive = metrics["substantive_count"]
    days = metrics["unique_days"]
    explicit = metrics["explicit_count"]
    total = len(metrics["mentions"])

    if score >= 520 and substantive >= 8 and days >= 4 and explicit >= 3:
        return "needs_report", "high"
    if score >= 330 and substantive >= 5 and days >= 3 and explicit >= 2:
        return "needs_report", "medium"
    if score >= 210 and substantive >= 3 and total >= 4:
        return "candidate", "low"
    return "no_report", "none"


def queue_item(stock, metrics, status, priority, has_report):
    evidence = []
    for mention in metrics["evidence"]:
        evidence.append({
            "tweet_id": mention.get("tweet_id"),
            "date": mention.get("date"),
            "url": mention.get("url"),
            "stance": mention.get("stance"),
            "mention_type": mention.get("mention_type"),
            "score": mention_score(mention),
            "reasons": (mention.get("reasons") or [])[:4],
            "text_preview": compact(mention.get("text"), 220),
        })

    return {
        "ticker": stock.get("ticker"),
        "company": stock.get("company"),
        "market": stock.get("exchange"),
        "industry": stock.get("industry"),
        "first_mention": stock.get("first_mention"),
        "last_mention": stock.get("last_mention"),
        "total_mentions": stock.get("total_mentions") or len(metrics["mentions"]),
        "unique_mention_days": metrics["unique_days"],
        "report_score": metrics["score"],
        "status": status,
        "priority": priority,
        "has_report": has_report,
        "explicit_stance_posts": metrics["explicit_count"],
        "substantive_posts": metrics["substantive_count"],
        "risk_posts": metrics["risk_count"],
        "high_conviction_posts": metrics["high_conviction_count"],
        "stance_counts": metrics["stance_counts"],
        "signal_terms": metrics["signal_terms"],
        "why": metrics["reasons"],
        "evidence": evidence,
    }


def build_queue(stocks_dir=STOCKS_DIR, reports_dir=REPORTS_DIR, update_candidates_path=UPDATE_CANDIDATES, include_existing=True):
    reports = report_files(reports_dir)
    updates = update_status_map(update_candidates_path)
    manifest = load_json(DATA_DIR / "db" / "manifest.json", {})
    items = []
    skipped = 0

    for stock_path in sorted(stocks_dir.glob("*.json")):
        stock = load_json(stock_path, {})
        ticker = (stock.get("ticker") or stock_path.stem).upper()
        stock["ticker"] = ticker
        metrics = score_stock(stock)
        if not metrics:
            skipped += 1
            continue
        has_report = ticker in reports
        status, priority = classify_report_need(metrics, has_report, updates.get(ticker))
        if status == "no_report":
            skipped += 1
            continue
        if has_report and not include_existing and status == "has_report":
            skipped += 1
            continue
        items.append(queue_item(stock, metrics, status, priority, has_report))

    status_rank = {
        "needs_regeneration": 0,
        "needs_update": 1,
        "needs_report": 2,
        "candidate": 3,
        "has_report": 4,
    }
    priority_rank = {"high": 0, "medium": 1, "low": 2, "none": 3}
    items.sort(key=lambda x: (status_rank.get(x["status"], 9), priority_rank.get(x["priority"], 9), -x["report_score"], x["ticker"]))

    next_reports = [item for item in items if item["status"] in {"needs_report", "candidate"}]
    existing = [item for item in items if item["status"] == "has_report"]
    updates_due = [item for item in items if item["status"] in {"needs_update", "needs_regeneration"}]

    return {
        "data_generated_at": manifest.get("generated_at"),
        "reports_available": len(reports),
        "stocks_scanned": len(list(stocks_dir.glob("*.json"))),
        "stocks_skipped": skipped,
        "summary": {
            "needs_report": sum(1 for item in items if item["status"] == "needs_report"),
            "candidate": sum(1 for item in items if item["status"] == "candidate"),
            "needs_update": sum(1 for item in items if item["status"] == "needs_update"),
            "needs_regeneration": sum(1 for item in items if item["status"] == "needs_regeneration"),
            "has_report": len(existing),
        },
        "next_reports": next_reports,
        "updates_due": updates_due,
        "existing_reports": existing,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stocks", default=str(STOCKS_DIR))
    ap.add_argument("--reports", default=str(REPORTS_DIR))
    ap.add_argument("--updates", default=str(UPDATE_CANDIDATES))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--hide-existing", action="store_true", help="omit tickers that already have clean reports")
    ap.add_argument("--print", action="store_true", help="print JSON instead of writing it")
    args = ap.parse_args()

    output = build_queue(
        stocks_dir=Path(args.stocks),
        reports_dir=Path(args.reports),
        update_candidates_path=Path(args.updates),
        include_existing=not args.hide_existing,
    )

    if args.print:
        print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        save_json(Path(args.out), output)
        summary = output["summary"]
        print(
            "Report queue: "
            f"{summary['needs_report']} needs_report, "
            f"{summary['candidate']} candidates, "
            f"{summary['needs_update']} needs_update, "
            f"{summary['needs_regeneration']} needs_regeneration."
        )


if __name__ == "__main__":
    main()
