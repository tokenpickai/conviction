#!/usr/bin/env python3
"""
Translate missing ticker detail reason snippets into Traditional Chinese.

This complements `audit_reason_translations.py`. Generated thesis reports are
Chinese, but the compact reason panels use extracted reason snippets. When a new
report introduces English snippets, this script writes translations to
data/reason_translations.json so the renderer can display them without code edits.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from profile_config import arg_value, load_profile, profile_paths  # noqa: E402

_PROFILE_ARG = arg_value(sys.argv, "--profile")
if _PROFILE_ARG:
    os.environ["CONVICTION_PROFILE"] = _PROFILE_ARG

import audit_reason_translations as audit  # noqa: E402
import serenity_render  # noqa: E402

OUT_PATH = ROOT / "data" / "reason_translations.json"
DEFAULT_MODEL = "claude-sonnet-4-6"


def load_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def load_dotenv(path=ROOT / ".env"):
    env = os.environ.copy()
    if not path.exists():
        return env
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in env:
            env[key] = value
    return env


def compact(text, limit=220):
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def missing_snippets(tickers=None, all_tickers=False):
    translations = audit.load_translation_keys()
    dd = serenity_render.dd_data()
    target = [t.upper() for t in tickers] if tickers else (sorted(dd) if all_tickers else sorted(serenity_render.REPORTS))
    out = []
    seen = set()
    for ticker in target:
        item = dd.get(ticker) or {}
        for panel in ("reasonsBull", "reasonsRisk"):
            for reason, url, date in item.get(panel) or []:
                if reason in translations or reason in seen:
                    continue
                if audit.englishy(reason):
                    seen.add(reason)
                    out.append({
                        "ticker": ticker,
                        "panel": panel,
                        "date": date,
                        "reason": reason,
                        "url": url,
                    })
    return out


def get_client(env, timeout):
    try:
        import anthropic
    except ImportError:
        print("ERROR: install anthropic first: pip install anthropic", file=sys.stderr)
        return None
    api_key = (env.get("ANTHROPIC_API_KEY") or "").strip()
    auth_token = (env.get("ANTHROPIC_AUTH_TOKEN") or "").strip()
    base_url = (env.get("ANTHROPIC_BASE_URL") or "").strip()
    if base_url and auth_token:
        return anthropic.Anthropic(auth_token=auth_token, base_url=base_url, timeout=float(timeout), max_retries=0)
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY is not set.", file=sys.stderr)
        return None
    return anthropic.Anthropic(api_key=api_key, timeout=float(timeout), max_retries=0)


def extract_json(text):
    text = (text or "").strip()
    if text.startswith("{") and text.endswith("}"):
        return json.loads(text)
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        raise ValueError("model did not return a JSON object")
    return json.loads(match.group(0))


def translate_with_model(snippets, model, timeout, profile):
    env = load_dotenv()
    client = get_client(env, timeout)
    if client is None:
        return None
    reasons = [item["reason"] for item in snippets]
    name = profile.get("display_name") or profile.get("handle") or "作者"
    pronoun = profile.get("pronoun_zh") or "作者"
    prompt = (
        "Translate these compact investment reason snippets into natural Traditional Chinese for a public "
        "investment thesis dashboard.\n"
        "Rules:\n"
        "- Return ONLY a JSON object mapping the exact original string to the translation.\n"
        "- Keep tickers, product names, abbreviations, and core jargon like CPO, InP, TPU, GPU, ATM, "
        "transceiver, photonics, neocloud in English when natural.\n"
        f"- The tracked author is {name}; refer to the author as {pronoun} when needed.\n"
        "- Keep each translation concise, usually one sentence.\n\n"
        + json.dumps(reasons, ensure_ascii=False, indent=2)
    )
    msg = client.messages.create(
        model=model,
        max_tokens=4000,
        temperature=0,
        system="You are a precise Traditional Chinese financial translation assistant. Output valid JSON only.",
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(block.text for block in msg.content if getattr(block, "type", "") == "text")
    data = extract_json(text)
    return {str(k): str(v) for k, v in data.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=None)
    ap.add_argument("--ticker", action="append", help="limit to one ticker; can be repeated")
    ap.add_argument("--all-tickers", action="store_true", help="translate reasons for every ticker visible in the dashboard")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--timeout", type=int, default=90)
    ap.add_argument("--batch-size", type=int, default=40)
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    profile = load_profile(args.profile)
    if args.profile:
        args.out = str(profile_paths(profile)["reason_translations"])

    missing = missing_snippets(args.ticker, all_tickers=args.all_tickers)
    if not missing:
        print("No missing reason translations.")
        return 0

    print(f"Found {len(missing)} missing reason translation(s):")
    for item in missing:
        print(f"- {item['ticker']} {item['panel']} {item['date']}: {item['reason']}")

    if args.dry_run:
        return 0

    existing = load_json(Path(args.out), {})
    written = 0
    batch_size = max(1, args.batch_size)
    for start in range(0, len(missing), batch_size):
        batch = missing[start:start + batch_size]
        translated = translate_with_model(batch, args.model, args.timeout, profile)
        if translated is None:
            return 1
        for item in batch:
            reason = item["reason"]
            if reason not in translated:
                raise RuntimeError(f"missing model translation for: {reason}")
            existing[reason] = translated[reason]
        save_json(Path(args.out), existing)
        written += len(batch)
        print(f"Translated {written}/{len(missing)} snippets.")

    print(f"Wrote {written} translation(s) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
