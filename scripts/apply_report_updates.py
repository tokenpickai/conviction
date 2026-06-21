#!/usr/bin/env python3
"""
Apply conservative, deterministic report updates from update candidates.

This is the lightweight automation layer between candidate detection and full
flagship report regeneration. It only writes compact dated updates when the new
posts have clear thesis signal; weak background mentions are marked reviewed by
advancing coverage_through so they do not keep resurfacing.
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
REPORTS_DIR = DATA_DIR / "reports"
DEFAULT_CANDIDATES = DATA_DIR / "report_update_candidates.json"

ACTIONABLE = {"update_candidate", "regeneration_candidate"}
LOW_SIGNAL_TYPES = {"background", "watchlist", "list", "comparison"}

TICKER_COPY = {
    "AAOI": {
        "title": "最新貼文強化雷射產能與美國供應鏈 thesis",
        "summary": "Serenity 最新貼文仍然偏多 $AAOI。這次新增重點不是改變原本 thesis，而是把 $AAOI 放在產業雷射與產能受限的背景下：她提到公司有 $471m/month projection、較多獨立供應來源，且供應位於美國，因此 bears 低估了供應鏈稀缺性。",
        "bullets": [
            "立場未反轉，仍偏多。",
            "新增重點：Serenity 強調產業仍受 laser / capacity 限制，而 $AAOI 有較清楚的供應位置。",
            "她把 $AAOI 視為 photonics 主題中已經驗證過的 smaller-cap idea，並提到早期大約在 $30 就開始看好。",
            "這是對原 thesis 的驗證與補強，不是新的重估報告；核心仍是稀缺光通訊能力與 2027 前後的收入爬坡。"
        ],
    },
    "AXTI": {
        "title": "InP thesis 獲得外部驗證，但仍需和稀釋風險分開看",
        "summary": "Serenity 最新貼文把 $AXTI 列為早期遭受大量質疑、但後來被外部資訊驗證的原創想法。她提到 Reuters、Epiwafer company earnings 與 institutions 對 InP substrate 供應鏈的驗證。這補強 InP substrate bottleneck thesis，但不等於移除先前提到的授權股數與稀釋風險。",
        "bullets": [
            "最新立場偏向 thesis validation：InP substrate 供應鏈邏輯被外部資料支持。",
            "這次更新補強的是產業驗證層，而不是否定先前的稀釋紅旗。",
            "閱讀 $AXTI 報告時，應把「InP thesis 是否正確」和「公司治理 / 稀釋是否可接受」分開判斷。",
            "若後續 Serenity 明確改變對稀釋的看法，才需要重寫完整報告。"
        ],
    },
    "NBIS": {
        "title": "Neocloud thesis 持續被股價表現驗證",
        "summary": "Serenity 最新貼文把 $NBIS 放在她三個核心 AI 主題之一：Neoclouds / Energy。她表示 $NBIS 是該主題裡的 top performer，並提到 YTD 已達 triple digit 表現。這比較像是 thesis played out 的確認，而不是新的 thesis 轉向。",
        "bullets": [
            "立場仍偏多，重點是原本 Neocloud / Energy thesis 正在被市場表現驗證。",
            "Serenity 把 $NBIS 與 photonics、memory 等核心主題並列，顯示它仍屬於她追蹤的主線。",
            "這次更新不應解讀成新的買點，只能說明原 thesis 的方向性已經 played out。",
            "後續真正需要更新的是估值、容量擴張與 energy availability 是否還能支撐 upside。"
        ],
    },
    "SIVE": {
        "title": "SIVE thesis 新增機構買盤與 JBL / GFS 合作驗證",
        "summary": "Serenity 最新貼文把 $SIVE 稱為她最成功的 idea 之一，並提到 Fidelity Research、JP Morgan 等 institutional buying，以及 JBL、GFS 等正式合作關係。這讓原本關於 silicon photonics / supply-chain validation 的 thesis 得到更強外部驗證。",
        "bullets": [
            "立場仍偏多，而且新增資訊屬於 thesis validation。",
            "Serenity 指出機構買盤與正式合作關係，降低了「只是敘事」的疑慮。",
            "JBL / GFS 等合作訊號讓 $SIVE 從概念題材更接近供應鏈落地。",
            "後續要觀察的是合作是否轉化為收入、毛利與持續訂單，而不是只停留在 partnership headline。"
        ],
    },
}


def load_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def max_post_date(posts):
    dates = [p.get("date") for p in posts if p.get("date")]
    return max(dates) if dates else ""


def meaningful_posts(posts):
    out = []
    for post in posts:
        stance = (post.get("stance") or "").lower()
        mention_type = post.get("mention_type") or ""
        if post.get("is_risk"):
            out.append(post)
        elif mention_type == "explicit_stance" and stance in {"bullish", "bearish", "mixed"}:
            out.append(post)
        elif post.get("conviction") in {"high", "medium"} and stance != "neutral":
            out.append(post)
    return out


def update_stance(posts):
    if any(p.get("is_risk") for p in posts):
        return "new_risk"
    stances = {(p.get("stance") or "").lower() for p in posts}
    if "bearish" in stances:
        return "more_cautious"
    if "mixed" in stances:
        return "more_cautious"
    if any((p.get("conviction") or "") == "high" for p in posts):
        return "more_bullish"
    return "still_bullish"


def generic_copy(ticker, posts):
    reasons = []
    for post in posts:
        for reason in post.get("reasons") or []:
            if reason and reason not in reasons:
                reasons.append(reason)
    reason_text = "、".join(reasons[:3]) if reasons else "新增貼文提供了比一般提及更高的 thesis signal"
    return {
        "title": f"{ticker} 出現新的 thesis validation 訊號",
        "summary": f"Serenity 最新貼文對 ${ticker} 提供了新的高訊號資訊：{reason_text}。目前較適合視為原報告的補充更新，而不是完整 thesis 重寫。",
        "bullets": [
            "此更新由最新 Serenity 貼文自動產生，僅收錄明確立場或高訊號內容。",
            f"新增訊號：{reason_text}。",
            "若後續出現立場反轉、重大風險或多篇高訊號貼文，才應進入完整報告重寫流程。",
        ],
    }


def existing_source_sets(report):
    sets = []
    for update in report.get("updates") or []:
        ids = {str(x) for x in update.get("source_tweet_ids") or []}
        if ids:
            sets.append(ids)
    return sets


def update_content_key(update):
    bullets = tuple((x or "").strip() for x in update.get("bullets") or [])
    return (
        (update.get("title") or "").strip(),
        (update.get("summary") or "").strip(),
        bullets,
    )


def is_duplicate_update(report, new_update):
    new_ids = set(new_update["source_tweet_ids"])
    if any(new_ids and new_ids.issubset(ids) for ids in existing_source_sets(report)):
        return "duplicate source tweets"
    new_key = update_content_key(new_update)
    if any(update_content_key(update) == new_key for update in report.get("updates") or []):
        return "duplicate update content"
    return ""


def build_update(ticker, candidate, posts):
    source_ids = []
    for post in posts:
        tweet_id = str(post.get("tweet_id") or "")
        if tweet_id and tweet_id not in source_ids:
            source_ids.append(tweet_id)
    copy = TICKER_COPY.get(ticker) or generic_copy(ticker, posts)
    return {
        "date": max_post_date(posts),
        "importance": candidate.get("importance") or "medium",
        "stance": update_stance(posts),
        "label": "最新更新",
        "title": copy["title"],
        "summary": copy["summary"],
        "bullets": copy["bullets"],
        "source_tweet_ids": source_ids,
        "generated_by": "scripts/apply_report_updates.py",
    }


def apply_candidates(candidates_path, reports_dir, dry_run=False):
    data = load_json(candidates_path, {})
    applied = []
    skipped = []
    advanced = []

    for candidate in data.get("candidates") or []:
        ticker = (candidate.get("ticker") or "").upper()
        if not ticker:
            continue
        report_path = reports_dir / f"{ticker}.json"
        report = load_json(report_path, None)
        if not isinstance(report, dict):
            skipped.append((ticker, "missing report"))
            continue

        posts = candidate.get("posts") or []
        latest_date = max_post_date(posts)
        if not latest_date:
            skipped.append((ticker, "no dated posts"))
            continue

        posts_for_update = meaningful_posts(posts)
        should_apply = candidate.get("classification") in ACTIONABLE and bool(posts_for_update)
        if should_apply:
            new_update = build_update(ticker, candidate, posts_for_update)
            duplicate_reason = is_duplicate_update(report, new_update)
            if duplicate_reason:
                skipped.append((ticker, duplicate_reason))
            else:
                updates = report.get("updates") or []
                report["updates"] = [new_update] + updates
                applied.append((ticker, new_update["date"], new_update["title"]))
        else:
            skipped.append((ticker, "low-signal/background only"))

        if latest_date > (report.get("coverage_through") or ""):
            report["coverage_through"] = latest_date
            advanced.append((ticker, latest_date))

        if not dry_run:
            save_json(report_path, report)

    return applied, skipped, advanced


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", default=str(DEFAULT_CANDIDATES))
    ap.add_argument("--reports", default=str(REPORTS_DIR))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    applied, skipped, advanced = apply_candidates(
        Path(args.candidates),
        Path(args.reports),
        dry_run=args.dry_run,
    )
    mode = "Dry run: " if args.dry_run else ""
    print(f"{mode}Applied {len(applied)} report updates; skipped {len(skipped)}; advanced coverage for {len(advanced)} reports.")
    for ticker, date, title in applied:
        print(f"  applied {ticker} {date}: {title}")
    for ticker, reason in skipped:
        print(f"  skipped {ticker}: {reason}")


if __name__ == "__main__":
    main()
