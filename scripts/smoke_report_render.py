#!/usr/bin/env python3
"""
Open the rendered static dashboard in a real browser and smoke-test report pages.

This catches failures that JSON validation cannot see: broken client-side report
rendering, missing ticker routes, polluted headings, and console/page errors.
"""

import argparse
import contextlib
import http.server
import json
import socket
import sys
import threading
from pathlib import Path

try:
    from profile_config import load_profile, profile_paths
except ImportError:  # pragma: no cover
    from scripts.profile_config import load_profile, profile_paths

ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "data" / "reports"


def load_json(path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def find_latest_html(root, prefix="serenity-tracker"):
    files = sorted(root.glob(f"{prefix}-*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def free_port():
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        return


def start_server(root):
    port = free_port()

    class Handler(QuietHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def report_paths(reports_dir, tickers):
    if tickers:
        return [reports_dir / f"{ticker.upper()}.json" for ticker in tickers]
    return sorted(reports_dir.glob("*.json"))


def browser_import():
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except Exception as exc:
        print("ERROR: Python Playwright is not installed or not usable.", file=sys.stderr)
        print("Install for smoke testing:", file=sys.stderr)
        print("  .venv/bin/python -m pip install playwright", file=sys.stderr)
        print("  .venv/bin/python -m playwright install chromium", file=sys.stderr)
        print(f"Original import error: {exc}", file=sys.stderr)
        sys.exit(2)


def smoke_one(page, base_url, html_url_path, report, profile_name):
    ticker = (report.get("ticker") or "").upper()
    title = report.get("title") or ""
    sections = report.get("sections") or []
    first_heading = (sections[0] or {}).get("heading") if sections else ""
    last_heading = (sections[-1] or {}).get("heading") if sections else ""
    url = f"{base_url}/{html_url_path}?v=smoke-report#{'ticker=' + ticker}"

    console_errors = []
    page_errors = []

    def on_console(msg):
        if msg.type == "error":
            console_errors.append(msg.text)

    def on_page_error(exc):
        page_errors.append(str(exc))

    page.on("console", on_console)
    page.on("pageerror", on_page_error)
    page.goto(url, wait_until="domcontentloaded")
    try:
        page.wait_for_selector("#ddPage", state="visible", timeout=2000)
    except Exception:
        pass
    page.wait_for_timeout(150)

    state = page.evaluate(
        """({ticker, title, firstHeading, lastHeading, profileName}) => {
          const text = document.body.innerText || '';
          const h3s = Array.from(document.querySelectorAll('.thesis-sec h3'));
          const headings = h3s.map(el => el.textContent.trim()).filter(Boolean);
          return {
            url: location.href,
            title: document.title,
            hasTicker: text.includes('$' + ticker) || text.includes(ticker),
            hasReportTitle: title ? text.includes(title) : false,
            hasFirstHeading: firstHeading ? text.includes(firstHeading) : false,
            hasLastHeading: lastHeading ? text.includes(lastHeading) : false,
            hasChartHeading: text.includes('$' + ticker + ' 自 ' + profileName + ' 首次提及以來的股價走勢'),
            hasTodayPosts: text.includes('今日 $' + ticker + ' 貼文'),
            reportHeadingCount: headings.length,
            glossaryInHeadings: document.querySelectorAll('.thesis-sec h3 .gloss').length + document.querySelectorAll('.thesis-sec h3 .glossary').length,
            headings: headings.slice(0, 12)
          };
        }""",
        {
            "ticker": ticker,
            "title": title,
            "firstHeading": first_heading,
            "lastHeading": last_heading,
            "profileName": profile_name,
        },
    )

    page.remove_listener("console", on_console)
    page.remove_listener("pageerror", on_page_error)

    errors = []
    if console_errors:
        errors.append(f"console errors: {console_errors[:3]}")
    if page_errors:
        errors.append(f"page errors: {page_errors[:3]}")
    if not state["hasReportTitle"]:
        errors.append("report title not visible")
    if not state["hasFirstHeading"]:
        errors.append("first report section heading not visible")
    if not state["hasLastHeading"]:
        errors.append("last report section heading not visible")
    if state["reportHeadingCount"] < 8:
        errors.append(f"expected at least 8 report headings, found {state['reportHeadingCount']}")
    if state["glossaryInHeadings"]:
        errors.append("glossary tooltip markup found inside report headings")

    warnings = []
    if not state["hasChartHeading"]:
        warnings.append("chart heading not visible")
    if not state["hasTodayPosts"]:
        warnings.append("today posts heading not visible")

    return {
        "ticker": ticker,
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "state": state,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=None)
    ap.add_argument("--html", help="Rendered dashboard HTML. Defaults to the selected profile's latest HTML.")
    ap.add_argument("--reports-dir", default=str(REPORTS_DIR))
    ap.add_argument("--ticker", action="append", help="Ticker to test. Can be repeated. Defaults to all reports.")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    profile = load_profile(args.profile)
    paths = profile_paths(profile)
    prefix = profile["dashboard"]["output_prefix"]
    if args.profile:
        args.reports_dir = str(paths["reports_dir"])

    html = Path(args.html).resolve() if args.html else find_latest_html(ROOT, prefix)
    if not html or not html.exists():
        print(f"ERROR: no rendered {prefix}-*.html found. Run scripts/serenity_render.py --profile {profile['slug']} first.", file=sys.stderr)
        return 2

    reports = []
    for path in report_paths(Path(args.reports_dir), args.ticker or []):
        report = load_json(path)
        if not report:
            print(f"ERROR: missing or invalid report {path}", file=sys.stderr)
            return 2
        reports.append(report)

    if not reports:
        result = {"passed": True, "reports_checked": 0, "results": []}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"Browser-smoked 0 report pages using {html.name}; profile has no published reports yet.")
        return 0

    sync_playwright = browser_import()
    server, port = start_server(ROOT)
    results = []
    try:
        html_url_path = html.relative_to(ROOT).as_posix()
    except ValueError:
        print(f"ERROR: rendered HTML must be inside {ROOT}", file=sys.stderr)
        return 2
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            for report in reports:
                results.append(smoke_one(page, f"http://127.0.0.1:{port}", html_url_path, report, profile["display_name"]))
            browser.close()
    except Exception as exc:
        print("ERROR: browser smoke test failed to run.", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        print("If Chromium is missing, run: .venv/bin/python -m playwright install chromium", file=sys.stderr)
        return 2
    finally:
        server.shutdown()

    passed = all(item["passed"] for item in results)
    if args.json:
        print(json.dumps({"passed": passed, "reports_checked": len(results), "results": results}, ensure_ascii=False, indent=2))
    else:
        for item in results:
            status = "PASS" if item["passed"] else "FAIL"
            print(f"{status} {item['ticker']}")
            for error in item["errors"]:
                print(f"  ERROR {error}")
            for warning in item["warnings"]:
                print(f"  WARN  {warning}")
        print(f"Browser-smoked {len(results)} report pages using {html.name}.")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
