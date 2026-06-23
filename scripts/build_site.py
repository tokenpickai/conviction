#!/usr/bin/env python3
"""
Build the static X Conviction portal.

Output:
  dist/index.html            portal page
  dist/serenity/index.html   Serenity dashboard
  dist/serenity/assets/      dashboard assets
"""

import argparse
import html
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
PROFILES_DIR = ROOT / "profiles"


def run(cmd):
    print("+ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def profile_configs():
    profiles = []
    for path in sorted(PROFILES_DIR.glob("*.json")):
        profile = load_json(path)
        profile["_path"] = str(path)
        profile.setdefault("slug", path.stem)
        profile.setdefault("display_name", profile["slug"].title())
        profile.setdefault("handle", "")
        profile.setdefault("avatar", "assets/serenity-avatar.jpg")
        profile.setdefault("portal", {})
        profile.setdefault("dashboard", {})
        profile["dashboard"].setdefault("output_prefix", f"{profile['slug']}-tracker")
        profiles.append(profile)
    if not profiles:
        raise SystemExit("No profiles found in profiles/*.json")
    return sorted(profiles, key=lambda profile: ((profile.get("portal") or {}).get("order", 999), profile["slug"]))


def latest_dashboard(prefix):
    files = sorted(ROOT.glob(f"{prefix}-*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise SystemExit(f"No {prefix} HTML found after render.")
    return files[0]


def copytree(src, dst):
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def profile_card(profile):
    slug = profile["slug"]
    name = profile.get("display_name") or slug.title()
    handle = (profile.get("handle") or "").lstrip("@")
    avatar = profile.get("avatar") or "assets/serenity-avatar.jpg"
    tag = (profile.get("portal") or {}).get("tag") or "進入"
    return (
        f'<a class="card" href="./{html.escape(slug)}/">\n'
        f'  <img src="./{html.escape(slug)}/{html.escape(avatar)}" alt="{html.escape(name)} avatar">\n'
        f'  <div><div class="name">{html.escape(name)}</div><div class="handle">@{html.escape(handle)}</div></div>\n'
        f'  <span class="tag">{html.escape(tag)}</span>\n'
        f'</a>'
    )


def portal_html(profiles):
    cards = "\n        ".join(profile_card(p) for p in profiles)
    return """<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>X Conviction</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700;800&display=swap" rel="stylesheet">
  <style>
    :root{--paper:#f7f4ef;--card:#fbfaf7;--ink:#252321;--muted:#817c72;--line:#ddd5c8;--accent:#1f5c4d;--soft:#e4f0e9}
    *{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:"Instrument Sans",system-ui,sans-serif}
    main{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:48px 20px}
    .wrap{width:min(860px,100%)}
    .eyebrow{font-family:"JetBrains Mono",monospace;font-size:12px;font-weight:800;color:var(--accent);letter-spacing:.04em;text-transform:uppercase}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px;margin-top:18px}
    a.card{display:flex;align-items:center;gap:14px;text-decoration:none;color:inherit;border:1px solid var(--line);background:var(--card);border-radius:10px;padding:16px;transition:border-color .16s ease,box-shadow .16s ease,transform .16s ease}
    a.card:hover{transform:translateY(-2px);border-color:rgba(31,92,77,.35);box-shadow:0 18px 34px -28px rgba(31,92,77,.9)}
    img{width:52px;height:52px;border-radius:50%;object-fit:cover;border:1px solid var(--line)}
    .name{font-size:20px;font-weight:800}.handle{font-family:"JetBrains Mono",monospace;font-size:12px;color:var(--muted);margin-top:3px}
    .tag{margin-left:auto;font-family:"JetBrains Mono",monospace;font-size:10px;font-weight:800;color:var(--accent);border:1px solid rgba(31,92,77,.24);background:var(--soft);border-radius:999px;padding:4px 8px;white-space:nowrap}
  </style>
</head>
<body>
  <main>
    <div class="wrap">
      <div class="eyebrow">X Conviction</div>
      <div class="grid">
        __PROFILE_CARDS__
      </div>
    </div>
  </main>
</body>
</html>
""".replace("__PROFILE_CARDS__", cards)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cname", default="xconviction.com", help="custom domain for GitHub Pages")
    args = ap.parse_args()

    profiles = profile_configs()

    if DIST.exists():
        shutil.rmtree(DIST)

    for profile in profiles:
        slug = profile["slug"]
        prefix = profile["dashboard"]["output_prefix"]
        run([sys.executable, "scripts/serenity_render.py", "--profile", slug])
        dashboard = latest_dashboard(prefix)
        profile_dir = DIST / slug
        profile_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(dashboard, profile_dir / "index.html")
        shutil.copyfile(dashboard, profile_dir / dashboard.name)
        copytree(ROOT / "assets", profile_dir / "assets")

    (DIST / "index.html").write_text(portal_html(profiles), encoding="utf-8")
    if args.cname:
        (DIST / "CNAME").write_text(args.cname.strip() + "\n", encoding="utf-8")
    print(f"built {DIST}")


if __name__ == "__main__":
    raise SystemExit(main())
