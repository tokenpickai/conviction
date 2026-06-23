#!/usr/bin/env python3
"""
Build the static X Conviction portal.

Output:
  dist/index.html            portal page
  dist/serenity/index.html   Serenity dashboard
  dist/serenity/assets/      dashboard assets
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"


def run(cmd):
    print("+ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def latest_dashboard():
    files = sorted(ROOT.glob("serenity-tracker-*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise SystemExit("No serenity-tracker HTML found after render.")
    return files[0]


def copytree(src, dst):
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def portal_html():
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
      <div class="eyebrow">精選 X 投資觀點追蹤</div>
      <div class="grid">
        <a class="card" href="./serenity/">
          <img src="./serenity/assets/serenity-avatar.jpg" alt="Serenity avatar">
          <div><div class="name">Serenity</div><div class="handle">@aleabitoreddit</div></div>
          <span class="tag">Open</span>
        </a>
      </div>
    </div>
  </main>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cname", default="xconviction.com", help="custom domain for GitHub Pages")
    args = ap.parse_args()

    run([sys.executable, "scripts/serenity_render.py"])
    dashboard = latest_dashboard()

    if DIST.exists():
        shutil.rmtree(DIST)
    serenity_dir = DIST / "serenity"
    serenity_dir.mkdir(parents=True, exist_ok=True)

    shutil.copyfile(dashboard, serenity_dir / "index.html")
    shutil.copyfile(dashboard, serenity_dir / dashboard.name)
    copytree(ROOT / "assets", serenity_dir / "assets")
    (DIST / "index.html").write_text(portal_html(), encoding="utf-8")
    if args.cname:
        (DIST / "CNAME").write_text(args.cname.strip() + "\n", encoding="utf-8")
    print(f"built {DIST}")


if __name__ == "__main__":
    raise SystemExit(main())
