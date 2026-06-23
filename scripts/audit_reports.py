#!/usr/bin/env python3
"""
Audit published thesis reports for dashboard hygiene issues.

This complements validate_reports.py. The validator checks report structure and
source grounding; this audit catches public-facing polish problems that have
shown up during review, such as duplicate update cards, missing metadata, and
untranslated compact reason panels.
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
REPORTS_DIR = DATA_DIR / "reports"
sys.path.insert(0, str(ROOT / "scripts"))

from profile_config import arg_value, load_profile, profile_paths  # noqa: E402

_PROFILE_ARG = arg_value(sys.argv, "--profile")
if _PROFILE_ARG:
    os.environ["CONVICTION_PROFILE"] = _PROFILE_ARG

import audit_reason_translations  # noqa: E402
import serenity_render  # noqa: E402


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class Finding:
    level: str
    code: str
    ticker: str
    message: str


@dataclass
class AuditResult:
    findings: list[Finding] = field(default_factory=list)

    def add(self, level, code, ticker, message):
        self.findings.append(Finding(level, code, ticker, message))

    @property
    def errors(self):
        return [f for f in self.findings if f.level == "error"]

    @property
    def warnings(self):
        return [f for f in self.findings if f.level == "warning"]


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def norm_text(text):
    return " ".join(str(text or "").split())


def update_key(update):
    return (
        norm_text(update.get("title")),
        norm_text(update.get("summary")),
        tuple(norm_text(x) for x in update.get("bullets") or []),
    )


def source_key(update):
    return tuple(sorted(str(x) for x in update.get("source_tweet_ids") or []))


def audit_report_metadata(path, report, result):
    ticker = (report.get("ticker") or path.stem).upper()
    if ticker != path.stem.upper():
        result.add("error", "ticker_filename_mismatch", ticker, f"{path.name} contains ticker {ticker}.")

    for key in ("ticker", "title", "subtitle", "core_label", "generated_at", "coverage_through"):
        if not norm_text(report.get(key)):
            result.add("error", "missing_metadata", ticker, f"Missing report metadata: {key}.")

    coverage = report.get("coverage_through") or ""
    if coverage and not DATE_RE.match(coverage):
        result.add("error", "bad_coverage_date", ticker, f"coverage_through is not YYYY-MM-DD: {coverage}.")

    generated = report.get("generated_at") or ""
    if generated and "T" not in generated:
        result.add("warning", "generated_at_not_iso", ticker, f"generated_at does not look ISO-like: {generated}.")


def audit_duplicate_updates(report, result):
    ticker = (report.get("ticker") or "").upper()
    seen_content = {}
    seen_sources = {}
    for index, update in enumerate(report.get("updates") or [], start=1):
        key = update_key(update)
        if key in seen_content:
            result.add(
                "error",
                "duplicate_update_content",
                ticker,
                f"Update {index} duplicates update {seen_content[key]} by title/summary/bullets.",
            )
        else:
            seen_content[key] = index

        src = source_key(update)
        if src:
            if src in seen_sources:
                result.add(
                    "error",
                    "duplicate_update_sources",
                    ticker,
                    f"Update {index} repeats source_tweet_ids from update {seen_sources[src]}.",
                )
            else:
                seen_sources[src] = index

        date = update.get("date") or ""
        if not DATE_RE.match(date):
            result.add("error", "bad_update_date", ticker, f"Update {index} has bad date: {date}.")
        if not norm_text(update.get("title")) or not norm_text(update.get("summary")):
            result.add("error", "missing_update_content", ticker, f"Update {index} needs title and summary.")


def audit_reason_panels(tickers, result, max_findings):
    translations = audit_reason_translations.load_translation_keys()
    dd = serenity_render.dd_data()
    count = 0
    for ticker in tickers:
        item = dd.get(ticker) or {}
        for panel in ("reasonsBull", "reasonsRisk"):
            for reason, _url, date in item.get(panel) or []:
                if reason in translations:
                    continue
                if audit_reason_translations.englishy(reason):
                    result.add(
                        "error",
                        "untranslated_reason",
                        ticker,
                        f"{panel} {date}: {reason}",
                    )
                    count += 1
                    if count >= max_findings:
                        return


def audit_reports(paths, max_reason_findings=80):
    result = AuditResult()
    reports = []
    for path in paths:
        report = load_json(path)
        reports.append((path, report))
        audit_report_metadata(path, report, result)
        audit_duplicate_updates(report, result)

    tickers = sorted((r.get("ticker") or p.stem).upper() for p, r in reports)
    audit_reason_panels(tickers, result, max_reason_findings)
    return result


def print_text(result):
    if not result.findings:
        print("PASS: report audit found no dashboard hygiene issues.")
        return
    print(f"FAIL: {len(result.errors)} errors, {len(result.warnings)} warnings.")
    for finding in result.findings:
        prefix = "ERROR" if finding.level == "error" else "WARN "
        print(f"{prefix} {finding.ticker} {finding.code}: {finding.message}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("reports", nargs="*", help="Report JSON paths. Defaults to data/reports/*.json")
    ap.add_argument("--profile", default=None)
    ap.add_argument("--reports-dir", default=str(REPORTS_DIR))
    ap.add_argument("--max-reason-findings", type=int, default=80)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if args.profile:
        args.reports_dir = str(profile_paths(load_profile(args.profile))["reports_dir"])

    paths = [Path(p) for p in args.reports] or sorted(Path(args.reports_dir).glob("*.json"))
    result = audit_reports(paths, max_reason_findings=args.max_reason_findings)

    if args.json:
        print(json.dumps({
            "passed": not result.errors,
            "errors": [f.__dict__ for f in result.errors],
            "warnings": [f.__dict__ for f in result.warnings],
        }, ensure_ascii=False, indent=2))
    else:
        print_text(result)

    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
