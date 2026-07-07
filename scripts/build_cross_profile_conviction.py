#!/usr/bin/env python3
"""
Build cross-profile conviction rankings.

This deterministic artifact compares stance signals across every configured
profile. It intentionally uses the stock databases, not LLM report prose, as
the scoring source.
"""

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path

try:
    from profile_config import PROFILES_DIR, ROOT, load_profile, profile_paths
except ImportError:  # pragma: no cover
    from scripts.profile_config import PROFILES_DIR, ROOT, load_profile, profile_paths


DEFAULT_OUT = ROOT / "data" / "cross_profile_conviction.json"
REASON_TRANSLATIONS_PATH = ROOT / "data" / "reason_translations.json"

INDUSTRY_OVERRIDES = {
    "ACMR": "China Semiconductor Equipment",
    "FORM": "Semiconductor Probe Cards/HBM Testing",
    "LPK": "Glass Substrate Equipment/CPO Waveguides",
    "MACRONIX": "NOR Flash/Memory",
    "STX": "HDD/Data Center Storage",
}

MARKET_OVERRIDES = {
    "2408": "TW",
    "2454": "TW",
    "3037": "TW",
    "3110": "JP",
    "ADVANTEST": "JP",
    "ARM": "UK",
    "ASML": "EU",
    "LPK": "EU",
    "MACRONIX": "TW",
    "SAMSUNG": "KR",
    "SIVE": "EU",
    "SK HYNIX": "KR",
    "SK_HYNIX": "KR",
    "TAIYOYUDEN": "JP",
    "VPEC": "TW",
    "WINBOND": "TW",
}


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def load_json(path, default):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


REASON_TRANSLATIONS = load_json(REASON_TRANSLATIONS_PATH, {})


def save_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def compact(text, limit=180):
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def translate_reason_text(text):
    if not text:
        return ""
    if text in REASON_TRANSLATIONS:
        return REASON_TRANSLATIONS[text]
    parts = [part.strip() for part in text.split(";") if part.strip()]
    if len(parts) <= 1:
        return REASON_TRANSLATIONS.get(text, text)
    translated = [REASON_TRANSLATIONS.get(part, part) for part in parts]
    return "；".join(translated)


def evidence_from_mentions(mentions, limit=3):
    evidence = []
    for mention in sorted(mentions, key=mention_strength, reverse=True)[:limit]:
        evidence.append({
            "tweet_id": mention.get("tweet_id"),
            "date": mention.get("date"),
            "url": mention.get("url"),
            "conviction": mention.get("conviction"),
            "reasons": mention.get("reasons") or [],
            "reason": compact("; ".join(mention.get("reasons") or []), 180),
            "text_preview": compact(mention.get("text"), 180),
        })
    return evidence


def configured_profiles(names=None):
    if names:
        selected = [load_profile(name) for name in names]
    else:
        selected = []
        for path in sorted(PROFILES_DIR.glob("*.json")):
            selected.append(load_profile(str(path)))
    return sorted(
        selected,
        key=lambda profile: ((profile.get("portal") or {}).get("order", 999), profile["slug"]),
    )


def unique_mentions(stock):
    by_id = {}
    for mention in stock.get("mentions") or []:
        tweet_id = mention.get("tweet_id")
        key = tweet_id or f"{mention.get('date')}:{mention.get('url')}:{mention.get('text')}"
        if not key:
            continue
        prev = by_id.get(key)
        prev_score = mention_strength(prev) if prev else -1
        current_score = mention_strength(mention)
        if prev is None or current_score > prev_score:
            by_id[key] = mention
    return sorted(by_id.values(), key=lambda item: ((item.get("date") or ""), (item.get("tweet_id") or "")))


def mention_strength(mention):
    if not mention:
        return 0
    score = 0
    if mention.get("mention_type") == "explicit_stance":
        score += 10
    if mention.get("stance") == "bullish":
        score += 4
    elif mention.get("stance") == "bearish":
        score += 4
    if mention.get("reasons"):
        score += min(6, len(mention.get("reasons") or []) * 2)
    if mention.get("is_risk"):
        score += 3
    if mention.get("conviction") == "high":
        score += 5
    elif mention.get("conviction") == "medium":
        score += 2
    return score


def ymd_to_tuple(value):
    try:
        return tuple(int(part) for part in value.split("-", 2))
    except Exception:
        return None


def days_between(a, b):
    import datetime

    aa = ymd_to_tuple(a)
    bb = ymd_to_tuple(b)
    if not aa or not bb:
        return None
    return (datetime.date(*bb) - datetime.date(*aa)).days


def profile_as_of(stock, mentions):
    dates = [m.get("date") for m in mentions if m.get("date")]
    if stock.get("last_mention"):
        dates.append(stock["last_mention"])
    return max(dates) if dates else None


def in_recent_window(date_value, as_of, days):
    delta = days_between(date_value, as_of)
    return delta is not None and 0 <= delta <= days - 1


def profile_report_info(paths, ticker):
    path = paths["reports_dir"] / f"{ticker}.json"
    if not path.exists():
        return {"has_report": False}
    report = load_json(path, {})
    return {
        "has_report": True,
        "title": report.get("title"),
        "core_label": report.get("core_label"),
        "coverage_through": report.get("coverage_through"),
    }


def market_tag(stock, ticker):
    override = MARKET_OVERRIDES.get(ticker)
    if override:
        return override
    price_symbol = (stock.get("price_symbol") or "").upper()
    suffix = price_symbol.rsplit(".", 1)[-1] if "." in price_symbol else ""
    if suffix in {"KS", "KQ"}:
        return "KR"
    if suffix in {"TW", "TWO"}:
        return "TW"
    if suffix in {"T"}:
        return "JP"
    if suffix in {"DE", "F", "ST", "AS", "PA", "MI", "SW"}:
        return "EU"
    if suffix in {"L"}:
        return "UK"
    if suffix in {"HK"}:
        return "HK"
    exchange = (stock.get("exchange") or "").lower()
    if "korea" in exchange:
        return "KR"
    if "taiwan" in exchange:
        return "TW"
    if "tokyo" in exchange or "japan" in exchange:
        return "JP"
    if "frankfurt" in exchange or "xetra" in exchange or "stockholm" in exchange or "euronext" in exchange:
        return "EU"
    if "hong kong" in exchange:
        return "HK"
    if exchange == "us":
        return "US"
    return ""


def classify_stance(bull, bear, neutral):
    directional = bull + bear
    if directional == 0:
        return "neutral" if neutral else "no_stance"
    net = bull - bear
    bull_share = bull / directional
    bear_share = bear / directional
    if net >= 2 and bull_share >= 0.65:
        return "bullish"
    if net > 0:
        return "mixed_bullish"
    if net <= -2 and bear_share >= 0.65:
        return "bearish"
    if net < 0:
        return "mixed_bearish"
    return "balanced"


def profile_signal(stock, profile, paths):
    mentions = unique_mentions(stock)
    explicit = [m for m in mentions if m.get("mention_type") == "explicit_stance"]
    bull = [m for m in explicit if m.get("stance") == "bullish"]
    bear = [m for m in explicit if m.get("stance") == "bearish"]
    neutral = [m for m in explicit if m.get("stance") == "neutral"]
    as_of = profile_as_of(stock, mentions)
    recent_bull = [m for m in bull if as_of and in_recent_window(m.get("date"), as_of, 28)]
    recent_bear = [m for m in bear if as_of and in_recent_window(m.get("date"), as_of, 28)]
    recent_mentions = [m for m in mentions if as_of and in_recent_window(m.get("date"), as_of, 28)]
    bull_days = {m.get("date") for m in bull if m.get("date")}
    bear_days = {m.get("date") for m in bear if m.get("date")}
    reasoned_bull = [m for m in bull if m.get("reasons")]
    risk_posts = [m for m in explicit if m.get("is_risk")]
    high_bull = [m for m in bull if m.get("conviction") == "high"]
    medium_bull = [m for m in bull if m.get("conviction") == "medium"]
    last_bull = max((m.get("date") for m in bull if m.get("date")), default=None)
    days_since_bull = days_between(last_bull, as_of) if last_bull and as_of else None

    directional = len(bull) + len(bear)
    net = len(bull) - len(bear)
    net_ratio = net / max(1, directional)
    recency_score = 0
    if days_since_bull is not None:
        recency_score = max(0, 12 - min(days_since_bull, 48) / 4)
    stance_score = max(0, net_ratio) * 32
    volume_score = min(22, len(bull) * 2.2 + len(bull_days) * 2)
    reason_score = min(12, len(reasoned_bull) * 1.5)
    conviction_score = min(14, len(high_bull) * 6 + len(medium_bull) * 3)
    recent_score = min(10, len(recent_bull) * 2.5 + max(0, len(recent_bull) - len(recent_bear)) * 1.5)
    report_score = 5 if (paths["reports_dir"] / f"{stock.get('ticker', '').upper()}.json").exists() else 0
    risk_penalty = min(24, len(bear) * 1.5 + len(risk_posts) * 2 + len(recent_bear) * 2.5)
    bullish_score = round(max(0, min(100, stance_score + volume_score + reason_score + conviction_score + recency_score + recent_score + report_score - risk_penalty)))

    bullish_evidence = evidence_from_mentions(bull)
    bearish_evidence = evidence_from_mentions(bear)

    ticker = (stock.get("ticker") or "").upper()
    industry = stock.get("industry") or INDUSTRY_OVERRIDES.get(ticker) or ""
    market = market_tag(stock, ticker)
    return {
        "profile": profile["slug"],
        "display_name": profile.get("display_name") or profile["slug"].title(),
        "handle": profile.get("handle"),
        "ticker": ticker,
        "company": stock.get("company") or ticker,
        "industry": industry,
        "exchange": stock.get("exchange") or "",
        "market": market,
        "first_mention": stock.get("first_mention"),
        "last_mention": stock.get("last_mention"),
        "total_mentions": len(mentions),
        "recent_mentions_28d": len(recent_mentions),
        "explicit_stance_posts": len(explicit),
        "bullish_posts": len(bull),
        "bearish_posts": len(bear),
        "neutral_posts": len(neutral),
        "bullish_days": len(bull_days),
        "bearish_days": len(bear_days),
        "recent_bullish_posts_28d": len(recent_bull),
        "recent_bearish_posts_28d": len(recent_bear),
        "high_conviction_bullish_posts": len(high_bull),
        "medium_conviction_bullish_posts": len(medium_bull),
        "reasoned_bullish_posts": len(reasoned_bull),
        "risk_posts": len(risk_posts),
        "stance": classify_stance(len(bull), len(bear), len(neutral)),
        "net_bullish_posts": net,
        "bullish_score": bullish_score,
        "as_of": as_of,
        "report": profile_report_info(paths, ticker),
        "evidence": bullish_evidence,
        "bullish_evidence": bullish_evidence,
        "bearish_evidence": bearish_evidence,
    }


def consensus_label(profile_rows):
    active = [row for row in profile_rows if row["explicit_stance_posts"] > 0]
    if not active:
        return "no_shared_stance"
    bullish = [row for row in active if row["net_bullish_posts"] > 0]
    bearish = [row for row in active if row["net_bullish_posts"] < 0]
    if len(active) >= 2 and len(bullish) == len(active):
        return "shared_bullish"
    if len(active) >= 2 and len(bearish) == len(active):
        return "shared_bearish"
    if bullish and bearish:
        return "divergent"
    if bullish:
        return "single_profile_bullish" if len(active) == 1 else "mixed_bullish"
    if bearish:
        return "single_profile_bearish" if len(active) == 1 else "mixed_bearish"
    return "balanced"


def evidence_reason(row, stance="bullish"):
    key = "bearish_evidence" if stance == "bearish" else "bullish_evidence"
    for evidence in row.get(key) or []:
        if evidence.get("reasons"):
            translated = [
                translate_reason_text(reason)
                for reason in evidence.get("reasons") or []
                if reason
            ]
            if translated:
                return "；".join(translated)
        if evidence.get("reason"):
            return translate_reason_text(evidence["reason"])
        if evidence.get("text_preview"):
            return evidence["text_preview"]
    return ""


def combined_thesis(consensus, bullish_profiles, bearish_profiles):
    if consensus == "divergent":
        bull = max(bullish_profiles, key=lambda row: row["bullish_score"], default=None)
        bear = min(bearish_profiles, key=lambda row: row["net_bullish_posts"], default=None)
        parts = []
        if bull:
            reason = evidence_reason(bull, "bullish")
            if reason:
                parts.append(f'{bull["display_name"]} 看多：{reason}')
        if bear:
            reason = evidence_reason(bear, "bearish")
            if reason:
                parts.append(f'{bear["display_name"]} 謹慎：{reason}')
            else:
                parts.append(f'{bear["display_name"]} 謹慎：bearish posts outnumber bullish posts')
        if parts:
            return {"label": "分歧點", "text": compact("；".join(parts), 230)}
        return {"label": "分歧點", "text": "profiles disagree on direction"}

    seen = set()
    reasons = []
    for row in sorted(bullish_profiles, key=lambda item: item["bullish_score"], reverse=True):
        reason = evidence_reason(row, "bullish")
        key = reason.lower()
        if reason and key not in seen:
            seen.add(key)
            reasons.append(reason)
        if len(reasons) >= 2:
            break
    if reasons:
        return {"label": "共同論點", "text": compact("；".join(reasons), 230)}
    return {"label": "共同論點", "text": "multiple profiles have net bullish explicit stance signals"}


def combined_item(ticker, profile_rows, profile_count):
    company = next((row.get("company") for row in profile_rows if row.get("company") and row.get("company") != ticker), ticker)
    industry = next((row.get("industry") for row in profile_rows if row.get("industry")), "")
    market = next((row.get("market") for row in profile_rows if row.get("market")), "")
    active = [row for row in profile_rows if row["explicit_stance_posts"] > 0]
    bullish_profiles = [row for row in active if row["net_bullish_posts"] > 0]
    bearish_profiles = [row for row in active if row["net_bullish_posts"] < 0]
    scores = [row["bullish_score"] for row in bullish_profiles]
    consensus_score = round(sum(scores) / len(scores)) if scores else 0
    if len(bullish_profiles) >= 2:
        consensus_score = min(100, consensus_score + min(10, len(bullish_profiles) * 3))
    if bearish_profiles:
        consensus_score = max(0, consensus_score - min(26, sum(abs(row["net_bullish_posts"]) for row in bearish_profiles) * 2))
    strongest = max(profile_rows, key=lambda row: (row["bullish_score"], row["net_bullish_posts"], row["recent_bullish_posts_28d"]))
    weakest = min(profile_rows, key=lambda row: (row["net_bullish_posts"], -row["bearish_posts"], row["bullish_score"]))
    divergence_score = 0
    if len(active) >= 2:
        raw_gap = max(row["net_bullish_posts"] for row in active) - min(row["net_bullish_posts"] for row in active)
        score_gap = max(row["bullish_score"] for row in active) - min(row["bullish_score"] for row in active)
        opposite = 18 if bullish_profiles and bearish_profiles else 0
        divergence_score = min(100, raw_gap * 4 + score_gap // 2 + opposite)

    consensus = consensus_label(profile_rows)

    return {
        "ticker": ticker,
        "company": company,
        "industry": industry,
        "market": market,
        "profile_count": profile_count,
        "active_profile_count": len(active),
        "bullish_profile_count": len(bullish_profiles),
        "bearish_profile_count": len(bearish_profiles),
        "consensus": consensus,
        "consensus_score": consensus_score,
        "divergence_score": divergence_score,
        "thesis": combined_thesis(consensus, bullish_profiles, bearish_profiles),
        "strongest_profile": strongest["profile"],
        "strongest_profile_score": strongest["bullish_score"],
        "most_cautious_profile": weakest["profile"],
        "profiles": {row["profile"]: row for row in sorted(profile_rows, key=lambda item: item["profile"])},
    }


def build(names=None):
    profiles = configured_profiles(names)
    by_ticker = defaultdict(list)

    for profile in profiles:
        paths = profile_paths(profile)
        for path in sorted(paths["stocks_dir"].glob("*.json")):
            stock = load_json(path, None)
            if not stock:
                continue
            ticker = (stock.get("ticker") or path.stem).upper()
            by_ticker[ticker].append(profile_signal(stock, profile, paths))

    items = []
    profile_count = len(profiles)
    for ticker, rows in sorted(by_ticker.items()):
        if len(rows) < 2:
            continue
        item = combined_item(ticker, rows, profile_count)
        if item["active_profile_count"] > 0:
            items.append(item)

    consensus_bullish = [
        item for item in items
        if item["consensus"] == "shared_bullish"
    ]
    consensus_bullish.sort(
        key=lambda item: (
            item["consensus_score"],
            item["bullish_profile_count"],
            min(row["bullish_score"] for row in item["profiles"].values() if row["net_bullish_posts"] > 0),
            sum(row["recent_bullish_posts_28d"] for row in item["profiles"].values()),
        ),
        reverse=True,
    )

    single_profile_bullish = [
        item for item in items
        if item["strongest_profile_score"] > 0
    ]
    single_profile_bullish.sort(
        key=lambda item: (
            item["strongest_profile_score"],
            item["profiles"][item["strongest_profile"]]["recent_bullish_posts_28d"],
            item["profiles"][item["strongest_profile"]]["bullish_posts"],
        ),
        reverse=True,
    )

    divergent = [item for item in items if item["consensus"] == "divergent"]
    divergent.sort(key=lambda item: (item["divergence_score"], item["consensus_score"]), reverse=True)

    return {
        "generated_at": utc_now(),
        "profiles": [
            {
                "slug": profile["slug"],
                "display_name": profile.get("display_name") or profile["slug"].title(),
                "handle": profile.get("handle"),
                "avatar": profile.get("avatar"),
            }
            for profile in profiles
        ],
        "summary": {
            "profile_count": profile_count,
            "shared_tickers": len(items),
            "shared_bullish": len(consensus_bullish),
            "divergent": len(divergent),
        },
        "rankings": {
            "consensus_bullish": [item["ticker"] for item in consensus_bullish[:50]],
            "single_profile_bullish": [item["ticker"] for item in single_profile_bullish[:50]],
            "divergent": [item["ticker"] for item in divergent[:50]],
        },
        "tickers": {item["ticker"]: item for item in sorted(items, key=lambda x: x["ticker"])},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", action="append", dest="profiles", help="profile slug/path; repeat to limit comparison")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--print", action="store_true")
    args = ap.parse_args()

    output = build(args.profiles)
    if args.print:
        print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        save_json(Path(args.out), output)
        print(
            "Cross-profile conviction: "
            f"{output['summary']['shared_bullish']} shared bullish, "
            f"{output['summary']['divergent']} divergent, "
            f"{output['summary']['shared_tickers']} shared tickers."
        )


if __name__ == "__main__":
    raise SystemExit(main())
