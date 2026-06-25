import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROFILES_DIR = ROOT / "profiles"


def arg_value(argv, flag, default=None):
    for idx, value in enumerate(argv):
        if value == flag and idx + 1 < len(argv):
            return argv[idx + 1]
        if value.startswith(flag + "="):
            return value.split("=", 1)[1]
    return default


def load_json(path, default):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def load_profile(name=None):
    raw = name or os.environ.get("CONVICTION_PROFILE") or "serenity"
    path = Path(raw)
    if not path.suffix:
        path = PROFILES_DIR / f"{raw}.json"
    if not path.is_absolute():
        path = (ROOT / path).resolve()

    profile = load_json(path, {})
    if not profile:
        profile = {
            "slug": "serenity",
            "display_name": "Serenity",
            "handle": "aleabitoreddit",
            "x_url": "https://x.com/aleabitoreddit",
            "avatar": "assets/serenity-avatar.jpg",
            "dashboard": {
                "output_prefix": "serenity-tracker",
                "data_dir": "data/db",
                "reports_dir": "data/reports",
            },
        }

    profile["_path"] = str(path)
    profile.setdefault("slug", path.stem if path.exists() else "serenity")
    profile.setdefault("display_name", profile["slug"].title())
    profile.setdefault("handle", "")
    profile.setdefault("pronoun_zh", "作者")
    profile.setdefault("analysis", {})
    profile["analysis"].setdefault("signal_strategy", "balanced")
    profile.setdefault("dashboard", {})
    profile["dashboard"].setdefault("output_prefix", f"{profile['slug']}-tracker")
    profile["dashboard"].setdefault("data_dir", "data/db")
    profile["dashboard"].setdefault("reports_dir", "data/reports")
    profile["dashboard"].setdefault("reason_translations", "data/reason_translations.json")
    profile["dashboard"].setdefault("report_queue", "data/report_queue.json")
    profile["dashboard"].setdefault("report_decisions", "data/report_decisions.json")
    profile["dashboard"].setdefault("report_failures", "data/report_generation_failures.json")
    profile["dashboard"].setdefault("report_update_candidates", "data/report_update_candidates.json")
    data_parent = str(Path(profile["dashboard"]["data_dir"]).parent)
    profile["dashboard"].setdefault("raw_tweets", f"{data_parent}/raw_tweets.json")
    profile["dashboard"].setdefault("fetch_state", f"{data_parent}/state.json")
    profile["dashboard"].setdefault("extracted", f"{data_parent}/extracted.json")
    profile["dashboard"].setdefault("ticker_map", f"{data_parent}/ticker_map.json")
    profile["dashboard"].setdefault("ticker_review", f"{data_parent}/ticker_review.json")
    profile["dashboard"].setdefault("prices_cache", f"{data_parent}/prices_cache")
    return profile


def dashboard_path(profile, key):
    return (ROOT / profile["dashboard"][key]).resolve()


def profile_paths(profile):
    data_dir = dashboard_path(profile, "data_dir")
    return {
        "profile": profile,
        "data_dir": data_dir,
        "stocks_dir": data_dir / "stocks",
        "manifest": data_dir / "manifest.json",
        "reports_dir": dashboard_path(profile, "reports_dir"),
        "reason_translations": dashboard_path(profile, "reason_translations"),
        "report_queue": dashboard_path(profile, "report_queue"),
        "report_decisions": dashboard_path(profile, "report_decisions"),
        "report_failures": dashboard_path(profile, "report_failures"),
        "report_update_candidates": dashboard_path(profile, "report_update_candidates"),
        "raw_tweets": dashboard_path(profile, "raw_tweets"),
        "fetch_state": dashboard_path(profile, "fetch_state"),
        "extracted": dashboard_path(profile, "extracted"),
        "ticker_map": dashboard_path(profile, "ticker_map"),
        "ticker_review": dashboard_path(profile, "ticker_review"),
        "prices_cache": dashboard_path(profile, "prices_cache"),
    }
