#!/usr/bin/env python3
"""
Validate generated Serenity thesis reports before they enter the dashboard.

This is a quality gate, not a style critic. It checks that reports are complete,
grounded in real local posts, and unlikely to be stale or accidentally rendered
as a draft.
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
REPORTS_DIR = DATA_DIR / "reports"
STOCKS_DIR = DATA_DIR / "db" / "stocks"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DRAFT_RE = re.compile(r"\b(v1|draft)\b|草稿|初稿", re.IGNORECASE)
STALE_STANCE_TERMS = {"bearish", "mixed", "neutral"}


@dataclass
class Issue:
    severity: str
    code: str
    message: str


@dataclass
class ReportResult:
    ticker: str
    path: str
    passed: bool = True
    warnings: list[Issue] = field(default_factory=list)
    errors: list[Issue] = field(default_factory=list)

    def add(self, severity, code, message):
        issue = Issue(severity, code, message)
        if severity == "error":
            self.errors.append(issue)
            self.passed = False
        else:
            self.warnings.append(issue)


def load_json(path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def text_blob(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(text_blob(v) for v in value)
    if isinstance(value, dict):
        return "\n".join(text_blob(v) for v in value.values())
    return ""


def user_facing_text(report):
    parts = [
        report.get("title"),
        report.get("subtitle"),
        report.get("core_label"),
        report.get("one_minute_summary"),
        report.get("sections"),
        report.get("final_takeaway"),
    ]
    for update in report.get("updates") or []:
        parts.append({
            "title": update.get("title"),
            "summary": update.get("summary"),
            "bullets": update.get("bullets"),
        })
    return "\n".join(text_blob(part) for part in parts)


def mention_index(stock):
    out = {}
    for mention in stock.get("mentions") or []:
        tweet_id = mention.get("tweet_id")
        if tweet_id:
            out[str(tweet_id)] = mention
    return out


def latest_explicit_mention(stock, coverage_through):
    mentions = [
        m for m in stock.get("mentions") or []
        if (m.get("date") or "") <= coverage_through and m.get("mention_type") == "explicit_stance"
    ]
    if not mentions:
        return None
    mentions.sort(key=lambda m: ((m.get("date") or ""), str(m.get("tweet_id") or "")))
    return mentions[-1]


def validate_report(path, stocks_dir=STOCKS_DIR, min_sections=8, max_sections=10, min_citations=8):
    report = load_json(path)
    ticker = path.stem.upper()
    result = ReportResult(ticker=ticker, path=str(path))
    if not isinstance(report, dict):
        result.add("error", "invalid_json", "Report is not valid JSON object.")
        return result

    ticker = (report.get("ticker") or ticker).upper()
    result.ticker = ticker
    stock = load_json(stocks_dir / f"{ticker}.json", {})
    if not stock:
        result.add("error", "missing_stock", f"Missing stock database file for {ticker}.")
        return result

    required_strings = ["ticker", "language", "title", "subtitle", "core_label", "coverage_through"]
    for key in required_strings:
        if not isinstance(report.get(key), str) or not report.get(key).strip():
            result.add("error", "missing_field", f"Missing or empty string field: {key}.")

    coverage = report.get("coverage_through") or ""
    if coverage and not DATE_RE.match(coverage):
        result.add("error", "bad_coverage_date", "coverage_through must be YYYY-MM-DD.")
    last_mention = stock.get("last_mention") or ""
    if coverage and last_mention and coverage > last_mention:
        result.add("error", "coverage_after_data", f"coverage_through {coverage} is after stock last_mention {last_mention}.")
    if coverage and last_mention and coverage < last_mention:
        result.add("warning", "coverage_not_latest", f"Report covers through {coverage}; local latest mention is {last_mention}.")

    summary = report.get("one_minute_summary")
    if not isinstance(summary, list) or len(summary) < 2:
        result.add("error", "bad_summary", "one_minute_summary should contain at least 2 items.")

    sections = report.get("sections")
    if not isinstance(sections, list):
        result.add("error", "bad_sections", "sections must be a list.")
        sections = []
    elif not (min_sections <= len(sections) <= max_sections):
        result.add("error", "section_count", f"Expected {min_sections}-{max_sections} sections, found {len(sections)}.")

    all_citations = []
    for idx, section in enumerate(sections, start=1):
        if not isinstance(section, dict):
            result.add("error", "bad_section", f"Section {idx} is not an object.")
            continue
        if not section.get("heading"):
            result.add("error", "missing_heading", f"Section {idx} is missing heading.")
        body = section.get("body")
        if not isinstance(body, list) or not any(str(p).strip() for p in body):
            result.add("error", "missing_body", f"Section {idx} must have non-empty body list.")
        citations = section.get("citations") or []
        if not isinstance(citations, list):
            result.add("error", "bad_citations", f"Section {idx} citations must be a list.")
            citations = []
        if not citations:
            result.add("warning", "section_no_citations", f"Section {idx} has no citations.")
        all_citations.extend(citations)

    updates = report.get("updates") or []
    if updates and not isinstance(updates, list):
        result.add("error", "bad_updates", "updates must be a list when present.")
        updates = []
    for idx, update in enumerate(updates, start=1):
        if not isinstance(update, dict):
            result.add("error", "bad_update", f"Update {idx} is not an object.")
            continue
        if not DATE_RE.match(update.get("date") or ""):
            result.add("error", "bad_update_date", f"Update {idx} date must be YYYY-MM-DD.")
        if not update.get("title") or not update.get("summary"):
            result.add("error", "bad_update_content", f"Update {idx} needs title and summary.")
        for tweet_id in update.get("source_tweet_ids") or []:
            all_citations.append({"tweet_id": tweet_id, "date": update.get("date"), "url": ""})

    source_posts = report.get("source_posts_used") or []
    if not isinstance(source_posts, list):
        result.add("error", "bad_sources", "source_posts_used must be a list.")
        source_posts = []
    all_citations.extend(source_posts)

    if len(source_posts) < min_citations:
        result.add("error", "not_enough_sources", f"Expected at least {min_citations} source_posts_used, found {len(source_posts)}.")

    stock_mentions = mention_index(stock)
    seen_citation_ids = set()
    for citation in all_citations:
        if not isinstance(citation, dict):
            result.add("error", "bad_citation", "Citation must be an object.")
            continue
        tweet_id = str(citation.get("tweet_id") or "").strip()
        if not tweet_id:
            result.add("error", "citation_missing_tweet", "Citation is missing tweet_id.")
            continue
        seen_citation_ids.add(tweet_id)
        mention = stock_mentions.get(tweet_id)
        if not mention:
            result.add("error", "citation_unknown_tweet", f"Citation tweet_id {tweet_id} not found in data/db/stocks/{ticker}.json.")
            continue
        cdate = citation.get("date")
        if cdate and mention.get("date") and cdate != mention.get("date"):
            result.add("warning", "citation_date_mismatch", f"Citation {tweet_id} date {cdate} differs from stock date {mention.get('date')}.")
        curl = citation.get("url")
        if curl and mention.get("url") and curl != mention.get("url"):
            result.add("warning", "citation_url_mismatch", f"Citation {tweet_id} URL differs from stock URL.")

    section_citation_ids = {
        str(c.get("tweet_id")) for section in sections
        for c in (section.get("citations") or []) if isinstance(c, dict) and c.get("tweet_id")
    }
    if len(section_citation_ids) < min_citations:
        result.add("error", "not_enough_section_citations", f"Expected at least {min_citations} unique section citations, found {len(section_citation_ids)}.")

    latest = latest_explicit_mention(stock, coverage)
    if latest:
        latest_id = str(latest.get("tweet_id"))
        latest_stance = (latest.get("stance") or "").lower()
        if latest_stance in STALE_STANCE_TERMS and latest_id not in seen_citation_ids:
            result.add(
                "warning",
                "latest_stance_not_cited",
                f"Latest explicit stance before coverage is {latest_stance} on {latest.get('date')} ({latest_id}) but report does not cite it.",
            )
        if latest_stance in {"bearish", "mixed"}:
            body = user_facing_text(report).lower()
            if "風險" not in body and "bear" not in body and "看空" not in body and "稀釋" not in body:
                result.add("error", "latest_stance_missing_context", "Latest stance is bearish/mixed but report lacks risk/bearish context.")

    visible = user_facing_text(report)
    if DRAFT_RE.search(visible):
        result.add("error", "draft_wording", "User-facing report text contains draft/v1 wording.")

    if not report.get("final_takeaway"):
        result.add("error", "missing_takeaway", "Missing final_takeaway.")

    return result


def result_to_dict(result):
    return {
        "ticker": result.ticker,
        "path": result.path,
        "passed": result.passed,
        "errors": [issue.__dict__ for issue in result.errors],
        "warnings": [issue.__dict__ for issue in result.warnings],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("reports", nargs="*", help="Report JSON paths. Defaults to data/reports/*.json")
    ap.add_argument("--reports-dir", default=str(REPORTS_DIR))
    ap.add_argument("--stocks-dir", default=str(STOCKS_DIR))
    ap.add_argument("--min-sections", type=int, default=8)
    ap.add_argument("--max-sections", type=int, default=10)
    ap.add_argument("--min-citations", type=int, default=8)
    ap.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = ap.parse_args()

    paths = [Path(p) for p in args.reports]
    if not paths:
        paths = sorted(Path(args.reports_dir).glob("*.json"))

    results = [
        validate_report(
            path,
            stocks_dir=Path(args.stocks_dir),
            min_sections=args.min_sections,
            max_sections=args.max_sections,
            min_citations=args.min_citations,
        )
        for path in paths
    ]

    if args.json:
        print(json.dumps({
            "passed": all(r.passed for r in results),
            "reports_checked": len(results),
            "results": [result_to_dict(r) for r in results],
        }, ensure_ascii=False, indent=2))
    else:
        for result in results:
            status = "PASS" if result.passed else "FAIL"
            print(f"{status} {result.ticker} ({Path(result.path).name})")
            for issue in result.errors:
                print(f"  ERROR {issue.code}: {issue.message}")
            for issue in result.warnings:
                print(f"  WARN  {issue.code}: {issue.message}")
        print(f"Checked {len(results)} reports.")

    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
