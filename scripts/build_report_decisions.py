#!/usr/bin/env python3
"""
Build a unified report decision layer for Serenity thesis coverage.

This script does not call an LLM. It merges the deterministic report queue and
the post-update checker into one small artifact that answers:

- Which existing reports need an update or full regeneration?
- Which uncovered tickers deserve a new flagship thesis?
- Which tickers should stay on watch?
- What should automation do next?
"""

import argparse
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
QUEUE_PATH = DATA_DIR / "report_queue.json"
UPDATES_PATH = DATA_DIR / "report_update_candidates.json"
DEFAULT_OUT = DATA_DIR / "report_decisions.json"


ACTION_LABELS = {
    "needs_regeneration": "regenerate_thesis",
    "needs_update": "write_update",
    "needs_report": "write_new_thesis",
    "candidate": "watch_for_more_signal",
    "has_report": "no_action",
}

PUBLIC_LABELS = {
    "regenerate_thesis": "重新生成投資論點",
    "write_update": "新增論點更新",
    "write_new_thesis": "撰寫新投資論點",
    "watch_for_more_signal": "觀察更多訊號",
    "no_action": "暫無動作",
}

AUTOMATION_ORDER = {
    "regenerate_thesis": 0,
    "write_update": 1,
    "write_new_thesis": 2,
    "watch_for_more_signal": 3,
    "no_action": 4,
}

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2, "none": 3, None: 4}


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def load_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def compact(text, limit=260):
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def evidence_preview(item, cap=3):
    evidence = []
    for mention in (item.get("evidence") or [])[:cap]:
        evidence.append({
            "tweet_id": mention.get("tweet_id"),
            "date": mention.get("date"),
            "url": mention.get("url"),
            "stance": mention.get("stance"),
            "score": mention.get("score"),
            "text_preview": compact(mention.get("text_preview"), 220),
        })
    return evidence


def update_preview(update_item):
    posts = []
    for post in (update_item.get("posts") or [])[:3]:
        posts.append({
            "tweet_id": post.get("tweet_id"),
            "date": post.get("date"),
            "url": post.get("url"),
            "stance": post.get("stance"),
            "score": post.get("score"),
            "text_preview": compact(post.get("text_preview"), 220),
        })
    return posts


def update_map(updates):
    return {
        (item.get("ticker") or "").upper(): item
        for item in updates.get("candidates") or []
        if item.get("ticker")
    }


def base_decision(item, action):
    priority = item.get("priority") or "none"
    return {
        "ticker": item.get("ticker"),
        "company": item.get("company"),
        "action": action,
        "public_label": PUBLIC_LABELS[action],
        "priority": priority,
        "has_report": bool(item.get("has_report")),
        "report_score": item.get("report_score"),
        "total_mentions": item.get("total_mentions"),
        "unique_mention_days": item.get("unique_mention_days"),
        "first_mention": item.get("first_mention"),
        "last_mention": item.get("last_mention"),
        "why": item.get("why") or [],
        "signal_terms": item.get("signal_terms") or [],
        "evidence": evidence_preview(item),
    }


def attach_update_context(decision, update_item):
    if not update_item:
        return decision
    decision["update_context"] = {
        "classification": update_item.get("classification"),
        "importance": update_item.get("importance"),
        "reason": update_item.get("reason"),
        "top_score": update_item.get("top_score"),
        "current_report_stance": update_item.get("current_report_stance"),
        "new_posts": update_item.get("new_posts"),
        "cutoff_date": update_item.get("cutoff_date"),
        "coverage_through": update_item.get("coverage_through"),
        "signal_terms": update_item.get("signal_terms") or [],
        "posts": update_preview(update_item),
    }
    if update_item.get("importance") in {"high", "medium"}:
        decision["priority"] = update_item.get("importance")
    if update_item.get("reason") and update_item.get("reason") not in decision["why"]:
        decision["why"] = [update_item["reason"]] + decision["why"]
    return decision


def decisions_from_queue(queue, updates, watch_limit):
    updates_by_ticker = update_map(updates)
    decisions = []

    for item in queue.get("updates_due") or []:
        status = item.get("status")
        action = ACTION_LABELS.get(status)
        if not action:
            continue
        decision = base_decision(item, action)
        decisions.append(attach_update_context(decision, updates_by_ticker.get((item.get("ticker") or "").upper())))

    for item in queue.get("next_reports") or []:
        status = item.get("status")
        action = ACTION_LABELS.get(status)
        if not action:
            continue
        decision = base_decision(item, action)
        decisions.append(decision)

    watch = []
    for item in queue.get("existing_reports") or []:
        if item.get("status") != "has_report":
            continue
        watch.append(base_decision(item, "no_action"))

    watch.sort(key=sort_key)
    decisions.extend(watch[:watch_limit])
    decisions.sort(key=sort_key)
    return decisions


def sort_key(item):
    return (
        AUTOMATION_ORDER.get(item.get("action"), 9),
        PRIORITY_ORDER.get(item.get("priority"), 9),
        -(item.get("report_score") or 0),
        item.get("ticker") or "",
    )


def build_output(queue_path=QUEUE_PATH, updates_path=UPDATES_PATH, watch_limit=25):
    queue = load_json(queue_path, {})
    updates = load_json(updates_path, {})
    decisions = decisions_from_queue(queue, updates, watch_limit)

    counts = {}
    for item in decisions:
        counts[item["action"]] = counts.get(item["action"], 0) + 1

    automation_next = [
        item for item in decisions
        if item["action"] in {"regenerate_thesis", "write_update", "write_new_thesis"}
    ]

    return {
        "generated_at": utc_now(),
        "data_generated_at": queue.get("data_generated_at") or updates.get("data_generated_at"),
        "source_files": {
            "queue": os.path.relpath(queue_path, ROOT),
            "updates": os.path.relpath(updates_path, ROOT),
        },
        "summary": {
            "total_decisions": len(decisions),
            "automation_ready": len(automation_next),
            "by_action": dict(sorted(counts.items())),
        },
        "automation_next": automation_next[:20],
        "decisions": decisions,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", default=str(QUEUE_PATH))
    ap.add_argument("--updates", default=str(UPDATES_PATH))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--watch-limit", type=int, default=25)
    ap.add_argument("--print", action="store_true", help="print JSON instead of writing it")
    args = ap.parse_args()

    output = build_output(
        queue_path=Path(args.queue),
        updates_path=Path(args.updates),
        watch_limit=args.watch_limit,
    )
    if args.print:
        print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        save_json(Path(args.out), output)
        summary = output["summary"]
        print(
            "Report decisions: "
            f"{summary['automation_ready']} automation-ready, "
            f"{summary['total_decisions']} total tracked."
        )


if __name__ == "__main__":
    main()
