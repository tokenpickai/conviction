#!/usr/bin/env python3
"""
Generate a long-form Serenity thesis report for one ticker.

MVP scope: one ticker at a time. The renderer consumes data/reports/{TICKER}.json.
"""

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

try:
    from profile_config import load_profile, profile_paths
except ImportError:  # pragma: no cover
    from scripts.profile_config import load_profile, profile_paths

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
DATA_DIR = ROOT / "data"
STOCKS_DIR = DATA_DIR / "db" / "stocks"
REPORTS_DIR = DATA_DIR / "reports"

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_ITEMS = 18
DEFAULT_TEXT_LIMIT = 650
DEFAULT_MAX_TOKENS = 6500
DEFAULT_TIMEOUT = 120
FAST_SYSTEM_PROMPT = """你是一位投資研究寫手。請根據 Serenity（@aleabitoreddit）的公開 X 貼文，為指定股票產生一版可靠的繁體中文 flagship thesis report。

要求：
- 只根據提供的貼文證據，不要補外部資料。
- 每段都要能回扣到 Serenity 原貼文。
- 寫得清楚、像人工整理，不要像機械摘要。
- 嚴格避免投資建議措辭。
- 輸出 ONLY valid JSON，不要 markdown fence。
- 請嚴格控制長度：one_minute_summary 正好 3 條；sections 正好 8 段；每段 body 正好 1 個段落；每段至少 1 個、最多 2 個 citations；final_takeaway 正好 2 條。
- 每個 body 段落請控制在 180 個中文字以內，避免輸出被截斷。
- 不要使用「草稿」「初稿」「v1」「draft」等字眼。

JSON schema:
{
  "ticker": "...",
  "language": "zh-Hant",
  "title": "...",
  "subtitle": "...",
  "core_label": "...",
  "one_minute_summary": ["不超過 80 字", "不超過 80 字", "不超過 80 字"],
  "sections": [
    {
      "heading": "一、...",
      "body": ["單一段落，不超過 180 字"],
      "citations": [
        {"tweet_id":"...", "date":"YYYY-MM-DD", "url":"...", "label":"...", "excerpt":"短摘錄"}
      ]
    }
  ],
  "final_takeaway": ["...", "..."],
  "quality_notes": {
    "reference_article_parity": ["這是可靠 v1，可再人工擴寫"],
    "known_limits": ["僅使用本次 curated evidence，不代表已讀完整 corpus"]
  }
}
"""


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


def profile_text(text, profile):
    name = profile.get("display_name") or profile.get("handle") or "作者"
    handle = (profile.get("handle") or "").lstrip("@")
    pronoun = profile.get("pronoun_zh") or "作者"
    return (
        text.replace("Serenity", name)
        .replace("@aleabitoreddit", f"@{handle}" if handle else name)
        .replace("她", pronoun)
    )


def load_json(path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


class ModelTimeoutError(TimeoutError):
    pass


def _timeout_handler(signum, frame):
    raise ModelTimeoutError("model call timed out")


def get_client(timeout=DEFAULT_TIMEOUT):
    try:
        import anthropic
    except ImportError:
        print("ERROR: install anthropic first: pip install anthropic", file=sys.stderr)
        sys.exit(1)

    auth_token = (os.environ.get("ANTHROPIC_AUTH_TOKEN") or "").strip()
    api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    base_url = (os.environ.get("ANTHROPIC_BASE_URL") or "").strip()
    if base_url and auth_token:
        return anthropic.Anthropic(auth_token=auth_token, base_url=base_url, timeout=float(timeout), max_retries=0)
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)
    return anthropic.Anthropic(api_key=api_key, timeout=float(timeout), max_retries=0)


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
    recent_explicit = list(reversed(explicit))
    recent_risks = list(reversed(risks))

    add(recent_explicit[:8])
    add(recent_risks[:8])
    add(explicit[:6])
    add(risks[:10])
    add(high[:30])
    add(recent[:18])

    if len(chosen) < max_items:
        add(unique)

    chosen = chosen[:max_items]
    chosen.sort(key=lambda x: (x.get("date") or "", x.get("tweet_id") or ""))
    return chosen


def build_prompt(stock, mentions, text_limit=DEFAULT_TEXT_LIMIT):
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
            "text": compact_text(m.get("text"), text_limit),
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


def build_fast_prompt(stock, mentions, text_limit=650):
    evidence = []
    for m in mentions:
        evidence.append({
            "tweet_id": m.get("tweet_id"),
            "date": m.get("date"),
            "url": m.get("url"),
            "stance": m.get("stance"),
            "mention_type": m.get("mention_type"),
            "is_risk": bool(m.get("is_risk")),
            "reasons": (m.get("reasons") or [])[:5],
            "text": compact_text(m.get("text"), text_limit),
        })
    payload = {
        "ticker": stock.get("ticker"),
        "company": stock.get("company"),
        "industry": stock.get("industry"),
        "market": stock.get("exchange"),
        "evidence_posts": evidence,
        "target_shape": [
            "一、Serenity 最初如何看這檔股票",
            "二、核心 thesis 是什麼",
            "三、公司 / 資產到底提供什麼能力",
            "四、供應鏈位置與產業邏輯",
            "五、哪些貼文提高或驗證了 thesis",
            "六、Serenity 如何比較同類標的",
            "七、風險、反方與需要驗證的地方",
            "八、今日如何理解這份 thesis"
        ],
    }
    return (
        "請生成一版 concise but high-quality flagship report。"
        "請嚴格寫 8 個 sections，每個 section 的 body 只能有 1 個段落。"
        "每個 section 至少附 1 個、最多 2 個 citations，優先引用最關鍵 tweet_id。"
        "不要超過 schema 指定長度，務必輸出完整 valid JSON。"
        "不要使用「草稿」「初稿」「v1」「draft」等字眼。\n\n"
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


def call_model(client, model, prompt, max_tokens=DEFAULT_MAX_TOKENS, timeout=DEFAULT_TIMEOUT, system_prompt=SYSTEM_PROMPT):
    last_err = None
    for attempt in range(1, 4):
        try:
            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(timeout)
            try:
                resp = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=[{"role": "user", "content": prompt}],
                )
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
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
    ap.add_argument("--profile", default=None)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--max-items", type=int, default=DEFAULT_MAX_ITEMS)
    ap.add_argument("--text-limit", type=int, default=DEFAULT_TEXT_LIMIT)
    ap.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="seconds per model attempt")
    ap.add_argument("--mode", choices=["full", "fast"], default="fast")
    ap.add_argument("--out", help="write report to this path instead of data/reports/{TICKER}.json")
    ap.add_argument("--dry-run", action="store_true", help="print prompt size and curated post IDs without calling the model")
    args = ap.parse_args()
    profile = load_profile(args.profile)
    paths = profile_paths(profile)
    stocks_dir = paths["stocks_dir"]
    reports_dir = paths["reports_dir"]

    ticker = args.ticker.upper()
    stock_path = stocks_dir / f"{ticker}.json"
    stock = load_json(stock_path, None)
    if not stock:
        print(f"ERROR: missing {stock_path}", file=sys.stderr)
        sys.exit(1)

    mentions = curate_mentions(stock, args.max_items)
    print(f"Curated {len(mentions)} evidence posts from {stock.get('total_mentions')} mentions.")
    if args.mode == "fast":
        prompt = profile_text(build_fast_prompt(stock, mentions, min(args.text_limit, 700)), profile)
        system_prompt = profile_text(FAST_SYSTEM_PROMPT, profile)
    else:
        prompt = profile_text(build_prompt(stock, mentions, args.text_limit), profile)
        system_prompt = profile_text(SYSTEM_PROMPT, profile)
    print(f"Prompt size: {len(prompt):,} chars; model={args.model}; max_tokens={args.max_tokens}; timeout={args.timeout}s.")
    if args.dry_run:
        for m in mentions:
            print(f"{m.get('date')} {m.get('tweet_id')} {m.get('stance')} {m.get('mention_type')}")
        return
    report = call_model(
        get_client(args.timeout),
        args.model,
        prompt,
        max_tokens=args.max_tokens,
        timeout=args.timeout,
        system_prompt=system_prompt,
    )
    report["ticker"] = ticker
    report["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    report["coverage_through"] = stock.get("last_mention") or max(
        (m.get("date") or "" for m in mentions),
        default="",
    )
    report["source_posts_used"] = [
        {"tweet_id": m.get("tweet_id"), "date": m.get("date"), "url": m.get("url")}
        for m in mentions
    ]
    out = Path(args.out).resolve() if args.out else reports_dir / f"{ticker}.json"
    save_json(out, report)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
