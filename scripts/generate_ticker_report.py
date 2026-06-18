#!/usr/bin/env python3
"""
Generate a long-form Serenity thesis report for one ticker.

MVP scope: one ticker at a time. The renderer consumes data/reports/{TICKER}.json.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
DATA_DIR = ROOT / "data"
STOCKS_DIR = DATA_DIR / "db" / "stocks"
REPORTS_DIR = DATA_DIR / "reports"

DEFAULT_MODEL = "claude-opus-4-6"


SYSTEM_PROMPT = """你是一位投資研究寫手。你的任務不是給投資建議，而是根據 Serenity（@aleabitoreddit）的公開 X 貼文，重建她對某一檔股票的完整投資論述。

品質目標：
- 寫成繁體中文長文，不要像機械摘要。
- 要有清楚的故事線：最初 thesis → 後續修正 → 確信度提高 → 產業鏈邏輯 → 已驗證部分 → 風險與反方思考 → 今日如何看。
- 每個重要判斷都要回扣到 Serenity 的原始貼文，不可以憑空補充。
- 可以解釋產業概念，但必須服務於 Serenity 的 thesis。
- 不要把所有貼文流水帳化；要萃取成投資邏輯。
- 語氣要像高品質研究文章，接近人工整理，不要像條列 AI 報告。
- 嚴格避免投資建議措辭；用「從 Serenity 的貼文來看」「她的框架是」「仍需驗證」等表述。

輸出 ONLY valid JSON，不要 markdown fence。Schema:
{
  "ticker": "AAOI",
  "language": "zh-Hant",
  "title": "...",
  "subtitle": "...",
  "core_label": "...",
  "one_minute_summary": ["...", "..."],
  "sections": [
    {
      "heading": "一、...",
      "body": ["段落1", "段落2"],
      "citations": [
        {"tweet_id":"...", "date":"YYYY-MM-DD", "url":"...", "label":"原始 thesis", "excerpt":"不超過 28 個中文字或 18 個英文詞的短摘錄"}
      ]
    }
  ],
  "final_takeaway": ["...", "..."],
  "quality_notes": {
    "reference_article_parity": ["..."],
    "known_limits": ["..."]
  }
}
"""


def load_json(path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def get_client():
    try:
        import anthropic
    except ImportError:
        print("ERROR: install anthropic first: pip install anthropic", file=sys.stderr)
        sys.exit(1)

    auth_token = (os.environ.get("ANTHROPIC_AUTH_TOKEN") or "").strip()
    api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    base_url = (os.environ.get("ANTHROPIC_BASE_URL") or "").strip()
    if base_url and auth_token:
        return anthropic.Anthropic(auth_token=auth_token, base_url=base_url, timeout=120.0)
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)
    return anthropic.Anthropic(api_key=api_key, timeout=120.0)


def compact_text(text, limit=1600):
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + " ..."


def score_mention(m):
    text = (m.get("text") or "").lower()
    score = 0
    if m.get("mention_type") == "explicit_stance":
        score += 20
    if m.get("is_risk"):
        score += 12
    if m.get("conviction") == "high":
        score += 12
    elif m.get("conviction") == "medium":
        score += 6
    views = ((m.get("engagement") or {}).get("views") or 0)
    likes = ((m.get("engagement") or {}).get("likes") or 0)
    score += min(18, views // 10000)
    score += min(12, likes // 25)
    keywords = [
        "800g", "1.6t", "laser", "lasers", "inp", "cpo", "pluggable",
        "cw", "amd", "nvda", "amzn", "msft", "maia", "trainium",
        "hyperscaler", "471m", "$471", "domestic", "texas", "scarce",
        "capacity", "favorite", "conviction", "bottleneck", "transceivers",
        "sive", "lumentum", "lite", "cohr", "jbl",
    ]
    score += sum(4 for k in keywords if k in text)
    return score


def curate_mentions(stock, max_items=70):
    mentions = stock.get("mentions") or []
    by_id = {}
    for m in mentions:
        tid = m.get("tweet_id")
        if not tid:
            continue
        prev = by_id.get(tid)
        if prev is None or score_mention(m) > score_mention(prev):
            by_id[tid] = m

    unique = sorted(by_id.values(), key=lambda x: (x.get("date") or "", x.get("tweet_id") or ""))

    chosen = []
    seen = set()

    def add(items):
        for item in items:
            tid = item.get("tweet_id")
            if tid and tid not in seen:
                chosen.append(item)
                seen.add(tid)

    explicit = [m for m in unique if m.get("mention_type") == "explicit_stance"]
    risks = [m for m in explicit if m.get("is_risk")]
    high = sorted(explicit, key=score_mention, reverse=True)
    recent = list(reversed(unique))

    add(explicit[:10])
    add(risks[:12])
    add(high[:35])
    add(recent[:18])

    if len(chosen) < max_items:
        add(unique)

    chosen = chosen[:max_items]
    chosen.sort(key=lambda x: (x.get("date") or "", x.get("tweet_id") or ""))
    return chosen


def build_prompt(stock, mentions):
    evidence = []
    for m in mentions:
        reasons = m.get("reasons") or []
        evidence.append({
            "tweet_id": m.get("tweet_id"),
            "date": m.get("date"),
            "url": m.get("url"),
            "stance": m.get("stance"),
            "mention_type": m.get("mention_type"),
            "is_risk": bool(m.get("is_risk")),
            "conviction": m.get("conviction"),
            "reasons": reasons[:8],
            "text": compact_text(m.get("text"), 1500),
        })

    payload = {
        "ticker": stock.get("ticker"),
        "company": stock.get("company"),
        "industry": stock.get("industry"),
        "market": stock.get("exchange"),
        "currency": stock.get("currency"),
        "first_mention": stock.get("first_mention"),
        "last_mention": stock.get("last_mention"),
        "total_mentions": stock.get("total_mentions"),
        "curated_evidence_posts": evidence,
        "requested_structure": [
            "開場：Serenity 從哪裡看到這檔股票，為什麼這不是普通光模組股",
            "Serenity 的時間線：初始 thesis、修正、提高確信、最新觀點",
            "公司到底做什麼：只解釋與 thesis 有關的部分",
            "產業鏈位置：AI data center → optical modules → lasers → InP / capacity",
            "真正瓶頸：需求不是問題，稀缺產能與製造 ramp 才是問題",
            "產品/架構週期：800G、1.6T、pluggable、CPO/NPO 如何並行",
            "hyperscaler / AMD / NVDA / AMZN / MSFT 供應鏈邏輯",
            "Serenity 有哪些修正或風險提示",
            "哪些 thesis 已經被驗證，哪些仍需觀察",
            "最後總結：從這檔股票學到的 Serenity 產業鏈思維",
        ],
    }
    return (
        "請根據以下資料，為這檔股票寫一篇繁體中文 Serenity thesis reconstruction report。\n"
        "務必讓文章有參考文章那種品質：每段先說投資邏輯，再放 Serenity 原貼文證據，再解釋為什麼重要。\n"
        "不要照抄參考文章；請用資料本身重建。\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def strip_fences(s):
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.endswith("```"):
            s = s.rsplit("```", 1)[0]
        if s.lstrip().startswith("json"):
            s = s.lstrip()[4:]
    return s.strip()


def call_model(client, model, prompt):
    last_err = None
    for attempt in range(1, 4):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=12000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
            return json.loads(strip_fences(raw))
        except Exception as exc:
            last_err = exc
            wait = 10 * attempt if "429" in str(exc) or "rate" in str(exc).lower() else 2 * attempt
            if attempt < 3:
                print(f"Model call failed ({exc}); retrying in {wait}s...", flush=True)
                time.sleep(wait)
    raise RuntimeError(f"Model call failed: {last_err}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--max-items", type=int, default=70)
    args = ap.parse_args()

    ticker = args.ticker.upper()
    stock_path = STOCKS_DIR / f"{ticker}.json"
    stock = load_json(stock_path, None)
    if not stock:
        print(f"ERROR: missing {stock_path}", file=sys.stderr)
        sys.exit(1)

    mentions = curate_mentions(stock, args.max_items)
    print(f"Curated {len(mentions)} evidence posts from {stock.get('total_mentions')} mentions.")
    prompt = build_prompt(stock, mentions)
    report = call_model(get_client(), args.model, prompt)
    report["ticker"] = ticker
    report["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    report["source_posts_used"] = [
        {"tweet_id": m.get("tweet_id"), "date": m.get("date"), "url": m.get("url")}
        for m in mentions
    ]
    out = REPORTS_DIR / f"{ticker}.json"
    save_json(out, report)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
