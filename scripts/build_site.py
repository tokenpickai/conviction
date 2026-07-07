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
CROSS_PROFILE_PATH = ROOT / "data" / "cross_profile_conviction.json"


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


def conviction_card():
    return (
        '<a class="card insight" href="./consensus/">\n'
        '  <div class="mark" aria-hidden="true"><svg viewBox="0 0 24 24" role="img"><path d="M18.901 1.153h3.68l-8.04 9.19L24 22.847h-7.406l-5.8-7.584-6.638 7.584H.474l8.6-9.83L0 1.153h7.594l5.243 6.932Zm-1.291 19.49h2.039L6.486 3.24H4.298Z"/></svg></div>\n'
        '  <div><div class="name">Conviction</div><div class="handle">比較不同 X profile 對同一檔股票的共識、分歧與最強看多訊號</div></div>\n'
        '  <span class="tag">比較</span>\n'
        '</a>'
    )


def portal_html(profiles):
    cards = "\n        ".join([conviction_card()] + [profile_card(p) for p in profiles])
    return """<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>X Conviction</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@500;700;800;900&display=swap" rel="stylesheet">
  <style>
    :root{--paper:#f9f7f3;--card:#fbf9f4;--ink:#1c1a17;--muted:#8a8479;--line:#dcd6c8;--accent:#1f5c4d;--soft:#e3ede8;--shadow:0 1px 0 rgba(0,0,0,.04),0 10px 28px -18px rgba(28,26,23,.38)}
    *{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:"Inter",system-ui,sans-serif;font-feature-settings:"tnum","ss01","cv11","cv02"}
    main{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:48px 20px}
    .wrap{width:min(980px,100%)}
    .eyebrow{font-family:"JetBrains Mono",monospace;font-size:12px;font-weight:800;color:var(--accent);letter-spacing:.04em;text-transform:uppercase}
    h1{font-size:clamp(34px,6vw,62px);line-height:.95;margin:8px 0 20px;font-weight:900;letter-spacing:0}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px;margin-top:18px}
    a.card{display:flex;align-items:center;gap:14px;text-decoration:none;color:inherit;border:1px solid var(--line);background:var(--card);border-radius:8px;padding:16px;box-shadow:var(--shadow);transition:border-color .16s ease,box-shadow .16s ease,transform .16s ease}
    a.card:hover{transform:translateY(-2px);border-color:var(--accent);box-shadow:0 18px 34px -28px rgba(31,92,77,.9)}
    img{width:52px;height:52px;border-radius:50%;object-fit:cover;border:1px solid var(--line)}
    .mark{width:52px;height:52px;border-radius:50%;display:grid;place-items:center;border:1px solid rgba(31,92,77,.28);background:var(--ink);color:var(--paper)}
    .mark svg{width:24px;height:24px;display:block;fill:currentColor}
    a.insight{grid-column:1/-1;border-color:rgba(31,92,77,.28);background:linear-gradient(90deg,rgba(31,92,77,.09),var(--card) 54%);padding:18px 20px}
    a.insight .name{font-size:24px}
    a.insight .handle{max-width:620px;white-space:normal;line-height:1.5}
    .name{font-size:20px;font-weight:800}.handle{font-family:"JetBrains Mono",monospace;font-size:12px;color:var(--muted);margin-top:3px}
    .tag{margin-left:auto;font-family:"JetBrains Mono",monospace;font-size:10px;font-weight:800;color:var(--accent);border:1px solid rgba(31,92,77,.24);background:var(--soft);border-radius:999px;padding:4px 8px;white-space:nowrap}
    @media(max-width:620px){main{padding:32px 12px}.grid{grid-template-columns:1fr}a.insight{align-items:flex-start}.tag{margin-left:0}.card{flex-wrap:wrap}}
  </style>
</head>
<body>
  <main>
    <div class="wrap">
      <div class="grid">
        __PROFILE_CARDS__
      </div>
    </div>
  </main>
</body>
</html>
""".replace("__PROFILE_CARDS__", cards)


def stance_label(value):
    return {
        "bullish": "看多",
        "mixed_bullish": "偏多",
        "balanced": "平衡",
        "mixed_bearish": "偏空",
        "bearish": "看空",
        "neutral": "中性",
        "no_stance": "未表態",
    }.get(value or "", value or "—")


def consensus_label(value):
    return {
        "shared_bullish": "共同看多",
        "single_profile_bullish": "單一強多",
        "mixed_bullish": "偏多但不一致",
        "divergent": "分歧",
        "shared_bearish": "共同看空",
        "balanced": "平衡",
        "no_shared_stance": "無共同表態",
    }.get(value or "", value or "—")


INDUSTRY_ZH = {
    "Optical Modules": "光通訊模組",
    "Optical Comms": "光通訊",
    "AI Cloud/GPU": "AI 雲端 / GPU",
    "AI Photonics/CPO Lasers": "AI 光子學 / CPO 雷射",
    "AI ASIC/Mobile Semiconductors": "AI ASIC / 行動半導體",
    "AI ASIC/Networking Chips": "AI ASIC / 網路晶片",
    "AI Package Substrates/MLCC": "AI 封裝基板 / MLCC",
    "AI Semis/CPO": "AI 半導體 / CPO",
    "AI Server PCB": "AI 伺服器 PCB",
    "AI Servers/PC Hardware": "AI 伺服器 / 個人電腦硬體",
    "AI/Connectivity Semiconductors": "AI / 連接晶片",
    "Advanced Packaging Equipment": "先進封裝設備",
    "Analog/Embedded Semiconductors": "類比 / 嵌入式半導體",
    "Analog/Power Semiconductors": "類比 / 功率半導體",
    "China Semiconductor Equipment": "中國半導體設備",
    "InP Substrates": "磷化銦基板",
    "AI Chips": "AI 晶片",
    "CPU/Foundry/Glass Substrate": "CPU / 晶圓代工 / 玻璃基板",
    "CPU/IP Licensing": "CPU / IP 授權",
    "E-glass/Advanced Materials": "E-glass / 先進材料",
    "Glass Substrate Equipment/CPO Waveguides": "玻璃基板設備 / CPO 光波導",
    "Glass Fiber/AI Substrates": "玻璃纖維 / AI 基板",
    "GPU/AI Chips": "GPU / AI 晶片",
    "HDD/Data Center Storage": "硬碟 / 資料中心儲存",
    "Hyperscaler": "超大規模雲端服務商",
    "IC Package Substrates": "IC 封裝基板",
    "IC Substrates/PCB": "IC 基板 / PCB",
    "Image Sensors/Electronics": "影像感測器 / 電子產品",
    "Industrial Gases/Semiconductor Materials": "工業氣體 / 半導體材料",
    "Industrial Holding Company": "工業控股公司",
    "Memory": "記憶體",
    "Memory/HBM": "記憶體 / HBM",
    "Memory/HBM (Korea)": "記憶體 / HBM（韓國）",
    "Memory/HBM/Semiconductors": "記憶體 / HBM / 半導體",
    "Memory/DRAM": "記憶體 / DRAM",
    "Memory/MCU Semiconductors": "記憶體 / MCU 半導體",
    "Memory/NAND": "記憶體 / NAND",
    "Memory Interface/IP": "記憶體介面 / IP",
    "NOR Flash/Memory": "NOR Flash / 記憶體",
    "Optical Components/Electronics": "光學元件 / 電子零組件",
    "Optical Comms/CPO": "光通訊 / CPO",
    "Optical Engine Packaging": "光引擎封裝",
    "Optical Fiber/Glass": "光纖 / 玻璃",
    "Optics/Photonics": "光學 / 光子學",
    "Passive Components": "被動元件",
    "Passive Components/MLCC": "被動元件 / MLCC",
    "PC Hardware": "個人電腦硬體",
    "Power/Automotive Semiconductors": "功率 / 車用半導體",
    "Semiconductor Equipment": "半導體設備",
    "Semiconductor Foundry": "半導體晶圓代工",
    "Semiconductor Lithography": "半導體微影設備",
    "Semiconductor Materials/CCL": "半導體材料 / CCL",
    "Semiconductor Metrology": "半導體量測設備",
    "Semiconductor Probe Cards/HBM Testing": "半導體探針卡 / HBM 測試",
    "Semiconductor Test Equipment": "半導體測試設備",
    "SOI Wafers": "SOI 晶圓",
    "Wafer Foundry": "晶圓代工",
    "Compound Semiconductors": "化合物半導體",
}

CONSENSUS_THESIS_ZH = {
    "SK HYNIX": "記憶體景氣受 AI 基建推動，獲利與目標價持續上修；Serenity 也把它視為高成長、高獲利的核心持股。",
    "MU": "共同看多 HBM / DDR5 供給吃緊、產能已被預訂到 2027，且 Micron 仍有估值重評空間。",
    "TSM": "共同論點集中在 AI 晶圓需求、議價能力與先進製程壟斷地位；營收動能與下游客戶 backlog 支撐重評。",
    "FORM": "看多 HBM / AI probe card 測試需求、毛利率改善與 CPO 測試機會，並受益於美國半導體供應鏈。",
    "LITE": "共同看多 Google OCS / TPU pod、NPO / CPO 光通訊需求，以及 hyperscaler ASIC 與 GPU 架構升級帶來的光學拉貨。",
    "TSEM": "看多其作為 silicon photonics / CPO 晶圓代工層的關鍵供應商，產能預訂與 NVIDIA 相關機會提高重評可能。",
    "LPK": "共同看多玻璃基板與 CPO 光波導設備的卡位，LIDE 技術有望從驗證走向量產，形成高槓桿瓶頸機會。",
    "ONTO": "共同論點是先進封裝與 HBM 檢測需求，尤其受益於 Samsung / HBM4 相關量測設備升級。",
    "ACMR": "共同看多中國半導體設備國產化、ACMR China 資產折價，以及美國母公司下半年擴張帶來的重評機會。",
    "MRVL": "看多 Maia / TPU 相關 ASIC 與互連設計機會，市場可能低估 2026-2027 客製晶片收入 ramp。",
    "MACRONIX": "共同看多 NOR Flash / 2D NAND 供給緊縮與漲價週期，Macronix 作為較純的 NOR Flash exposure 具備重評空間。",
    "INTC": "共同論點是美國半導體政策、在地供應鏈與自有晶圓廠價值；AI CPU 需求可能強化其產能與議價能力。",
    "SIVE": "Serenity 看多 CPO / silicon photonics 雷射瓶頸與小市值 upside；Jukan 對客戶定位、商業化與競爭格局更謹慎。",
    "AVGO": "Serenity 看多 Google TPU ASIC 與 hyperscaler ASIC exposure；Jukan 擔心 Google 轉向 COT 模式後 Broadcom 角色降級。",
    "SAMSUNG": "Serenity 看多記憶體獲利與 HBM / foundry exposure；Jukan 對中國競爭與部分市場領導地位流失更謹慎。",
    "POET": "Serenity 認為 POET 長線仍有光引擎機會但時間偏早；Jukan 對 NDA / 客戶溝通與執行風險明顯更負面。",
    "RMBS": "Serenity 看多 HBM memory IP 授權與高毛利重評；Jukan 則偏好其他記憶體週期標的而排除 Rambus。",
    "2408": "Serenity 看多 Nanya 在 legacy / specialty DRAM 漲價週期中的獲利彈性；Jukan 擔心中國 DRAM 擴產壓力。",
    "2454": "Serenity 看多 MediaTek 未來兩年表現；Jukan 擔心 Google TPU 模式轉向後，MediaTek 可能降為 IP / design service 角色。",
    "STX": "Serenity 把 STX 視為 AI capex 與儲存需求受益者；Jukan 認為 HDD 股估值過高，需求放緩後 EPS 風險很大。",
    "TER": "Serenity 看多自動化替代人力的長期趨勢；Jukan 對 Teradyne 相關消息解讀偏負面。",
}


def industry_label(industry):
    if not industry:
        return "未分類"
    zh = INDUSTRY_ZH.get(industry)
    if zh:
        return f"{zh} ({industry})"
    return industry


def profile_chip(slug, row):
    score = row.get("bullish_score") or 0
    stance = row.get("stance") or "no_stance"
    cls = "bull" if row.get("net_bullish_posts", 0) > 0 else ("bear" if row.get("net_bullish_posts", 0) < 0 else "flat")
    href = f"../{html.escape(slug)}/#ticker={html.escape(row.get('ticker') or '')}"
    return (
        f'<a class="chip {cls}" href="{href}">'
        f'<span>{html.escape(row.get("display_name") or slug)}</span>'
        f'<b>{score}</b>'
        f'<em>{html.escape(stance_label(stance))}</em>'
        '</a>'
    )


def conviction_item(data, ticker, mode):
    item = data["tickers"][ticker]
    profiles = item.get("profiles") or {}
    chips = "".join(profile_chip(slug, row) for slug, row in sorted(profiles.items()))
    if mode == "divergent":
        metric_label = "分歧"
        metric = item.get("divergence_score") or 0
    elif mode == "single":
        metric_label = html.escape(item.get("strongest_profile") or "score")
        metric = item.get("strongest_profile_score") or 0
    else:
        metric_label = "共識"
        metric = item.get("consensus_score") or 0
    description = industry_label(item.get("industry"))
    market = item.get("market") or ""
    market_badge = f'<span class="market-tag">{html.escape(market)}</span>' if market else ""
    thesis = item.get("thesis") or {}
    thesis_label = thesis.get("label") or ("分歧點" if mode == "divergent" else "共同論點")
    thesis_text = CONSENSUS_THESIS_ZH.get(ticker) or thesis.get("text") or ""
    thesis_html = (
        f'<div class="thesis"><span>{html.escape(thesis_label)}</span>{html.escape(thesis_text)}</div>'
        if thesis_text else ""
    )
    return (
        '<article class="idea">'
        f'<div class="idea-head"><div><div class="ticker-row"><div class="ticker">{html.escape(ticker)}</div>{market_badge}</div>'
        f'<h3>{html.escape(item.get("company") or ticker)}</h3>'
        f'<p>{html.escape(description)}</p>{thesis_html}</div>'
        f'<div class="score"><b>{metric}</b><span>{metric_label}</span></div></div>'
        f'<div class="state">{html.escape(consensus_label(item.get("consensus")))}</div>'
        f'<div class="chips">{chips}</div>'
        '</article>'
    )


def conviction_section(title, kicker, data, ranking_name, mode):
    tickers = (data.get("rankings") or {}).get(ranking_name) or []
    body = "".join(conviction_item(data, ticker, mode) for ticker in tickers[:12])
    if not body:
        body = '<div class="empty">目前沒有符合條件的交集。</div>'
    return (
        '<section class="period-sec">'
        f'<div class="sec"><div class="sechd"><div class="st">{html.escape(title)}</div>'
        f'<div class="datepill">{html.escape(kicker)}</div></div></div>'
        f'<div class="daypad"><div class="ideas">{body}</div></div>'
        '</section>'
    )


def profile_avatar_stack(profiles):
    avatars = []
    for profile in profiles:
        avatar = profile.get("avatar") or "assets/serenity-avatar.jpg"
        name = profile.get("display_name") or profile.get("slug") or ""
        avatars.append(
            f'<img src="./{html.escape(avatar)}" alt="{html.escape(name)}" title="{html.escape(name)}">'
        )
    return '<div class="profile-stack">' + "".join(avatars) + "</div>"


def conviction_html(data):
    summary = data.get("summary") or {}
    profile_badges = profile_avatar_stack(data.get("profiles") or [])
    sections = "\n".join([
        conviction_section("共同看多", "Consensus Bullish", data, "consensus_bullish", "consensus"),
        conviction_section("觀點分歧", "Divergence Watch", data, "divergent", "divergent"),
    ])
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Consensus</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@500;700;800;900&display=swap" rel="stylesheet">
  <style>
    :root{{--paper:#f9f7f3;--card:#fbf9f4;--ink:#1c1a17;--ink-soft:#55514a;--ink-faint:#8a8479;--line:#dcd6c8;--line-strong:#c6bfae;--accent:#1f5c4d;--accent-soft:#e3ede8;--bull:#1f7a4d;--bull-bg:#e6f1e9;--bear:#a8392b;--bear-bg:#f4e3df;--neutral:#8a7a3f;--neutral-bg:#f0ebd9;--gold:#b8893a;--mono:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,monospace;--sans:'Inter',ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;--serif:'Inter',ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;--shadow:0 1px 0 rgba(0,0,0,.04),0 10px 28px -18px rgba(28,26,23,.38)}}
    *{{box-sizing:border-box;margin:0;padding:0}}body{{background:var(--paper);font-family:var(--sans);font-feature-settings:"tnum","ss01","cv11","cv02";color:var(--ink)}}a{{color:inherit}}
    .main{{min-height:100vh;width:min(1280px,100%);margin:0 auto;padding-bottom:54px}}.crumb{{font-family:var(--mono);font-size:11px;color:var(--ink-faint);display:flex;align-items:center;gap:7px;flex-wrap:wrap;padding:24px 44px 0}}.crumb a{{color:var(--ink-soft);text-decoration:none;border-bottom:1px solid transparent}}.crumb a:hover{{color:var(--accent);border-bottom-color:rgba(31,92,77,.35)}}.crumb b{{color:var(--ink);font-weight:800}}.crumb .sep{{color:var(--line-strong)}}
    .hero{{padding:34px 44px 10px}}.hero-card{{border:1px solid var(--line);background:linear-gradient(180deg,rgba(31,92,77,.06),var(--card) 62%);border-radius:8px;box-shadow:var(--shadow);padding:24px 26px;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:24px;align-items:end}}.hero-copy{{display:block}}.eyebrow{{font-family:var(--mono);font-size:11px;font-weight:900;color:var(--accent);letter-spacing:.04em;text-transform:uppercase}}h1{{font-family:var(--serif);font-size:clamp(34px,5vw,58px);font-weight:900;line-height:1;margin:8px 0 10px;letter-spacing:0}}p{{color:var(--ink-soft);line-height:1.65;font-size:14px;max-width:760px}}.profile-stack{{display:flex;align-items:center;flex-wrap:wrap;margin-top:12px;padding-left:1px}}.profile-stack img{{width:34px;height:34px;border-radius:50%;object-fit:cover;border:2px solid var(--card);box-shadow:0 0 0 1px var(--line)}}.profile-stack img+img{{margin-left:-10px}}
    .stats{{display:grid;grid-template-columns:repeat(3,104px);gap:8px}}.stat{{border:1px solid var(--line);background:var(--card);border-radius:8px;padding:11px 12px}}.stat b{{display:block;font-family:var(--serif);font-size:28px;line-height:1;color:var(--ink)}}.stat span{{font-family:var(--mono);font-size:10px;color:var(--ink-faint);font-weight:800}}
    .sec{{padding:34px 44px 10px}}.sechd{{display:flex;align-items:baseline;gap:14px;border-bottom:2px solid var(--ink);padding-bottom:12px;margin-bottom:8px}}.sechd .st{{font-family:var(--serif);font-weight:900;font-size:30px;display:inline-flex;align-items:center;gap:10px}}.sechd .datepill{{font-family:var(--mono);font-weight:500;font-size:13px;color:var(--ink-soft);background:transparent;padding:0;border-radius:0;letter-spacing:0}}.daypad{{padding:0 44px}}.subhd{{font-family:var(--mono);font-size:12px;color:var(--ink-faint);margin:18px 0 14px}}
    .ideas{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}}.idea{{position:relative;display:flex;flex-direction:column;border:1px solid rgba(31,92,77,.2);border-radius:8px;background:linear-gradient(180deg,rgba(31,92,77,.045),var(--card) 58%);padding:15px 16px;min-width:0;box-shadow:var(--shadow);transition:border-color .16s ease,box-shadow .16s ease,transform .16s ease}}.idea:hover{{transform:translateY(-2px);border-color:rgba(31,92,77,.45);box-shadow:0 18px 34px -26px rgba(31,92,77,.75)}}.idea::before{{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;border-radius:8px 0 0 8px;background:var(--accent)}}.idea-head{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;align-items:start}}
    .ticker-row{{display:flex;align-items:center;gap:7px;min-width:0;flex-wrap:wrap}}.ticker{{font-family:var(--mono);font-size:13px;font-weight:900;color:var(--ink)}}.market-tag{{display:inline-flex;align-items:center;height:18px;border:1px solid rgba(31,92,77,.22);border-radius:999px;background:rgba(31,92,77,.07);padding:0 6px;font-family:var(--mono);font-size:9.5px;font-weight:900;color:var(--accent);line-height:1}}h3{{font-family:var(--serif);font-size:17px;font-weight:900;line-height:1.28;color:var(--ink);margin:7px 0 6px;letter-spacing:0}}.idea p{{font-size:12.5px;line-height:1.6;color:var(--ink-soft);min-height:40px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}.thesis{{margin-top:9px;border-top:1px solid rgba(198,191,174,.55);padding-top:9px;color:var(--ink-soft);font-size:12px;line-height:1.55;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}.thesis span{{font-family:var(--mono);font-size:10px;font-weight:900;color:var(--accent);margin-right:6px;white-space:nowrap}}
    .score{{text-align:right;font-family:var(--mono);color:var(--ink-faint);min-width:48px}}.score b{{display:block;font-size:27px;line-height:1;color:var(--accent)}}.score span{{display:block;font-size:9.5px;font-weight:800;text-transform:uppercase;letter-spacing:.03em;margin-top:3px}}.state{{display:inline-flex;align-self:flex-start;margin-top:12px;font-family:var(--mono);font-size:10.5px;font-weight:800;color:var(--accent);background:var(--accent-soft);border:1px solid rgba(31,92,77,.24);border-radius:999px;padding:3px 8px}}
    .chips{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}}.chip{{display:grid;grid-template-columns:1fr auto;gap:2px 8px;text-decoration:none;border:1px solid var(--line);border-radius:8px;padding:9px;color:inherit;background:var(--card);transition:border-color .16s ease,transform .16s ease}}.chip:hover{{transform:translateY(-1px);border-color:var(--accent)}}.chip span{{font-weight:800;font-size:13px}}.chip b{{font-family:var(--mono);font-size:16px}}.chip em{{grid-column:1/3;font-style:normal;font-family:var(--mono);font-size:10px;color:var(--ink-faint);font-weight:800}}.chip.bull{{background:var(--bull-bg);border-color:rgba(31,122,77,.2)}}.chip.bull b,.chip.bull em{{color:var(--bull)}}.chip.bear{{background:var(--bear-bg);border-color:rgba(168,57,43,.22)}}.chip.bear b,.chip.bear em{{color:var(--bear)}}.empty{{border:1px dashed var(--line-strong);border-radius:8px;padding:16px;color:var(--ink-soft);background:var(--card);font-size:12.5px}}
    @media(max-width:1050px){{.ideas{{grid-template-columns:1fr 1fr}}.hero-card{{grid-template-columns:1fr}}.stats{{grid-template-columns:repeat(3,minmax(0,1fr))}}}}
    @media(max-width:720px){{.crumb,.hero,.sec,.daypad{{padding-left:14px;padding-right:14px}}.ideas{{grid-template-columns:1fr}}.chips{{grid-template-columns:1fr}}.sechd{{flex-wrap:wrap}}.sechd .st{{font-size:24px}}}}
  </style>
</head>
<body>
  <main class="main">
    <div class="crumb"><a href="../">X Conviction</a><span class="sep">/</span><b>Consensus</b></div>
    <div class="hero">
      <div class="hero-card">
        <div class="hero-copy">
          <div>
          <div class="eyebrow">Cross-Profile Consensus</div>
          <p>彙整不同 X profile 對同一檔股票的方向表態、理由深度與近期訊號，找出共同看多與明顯分歧。</p>
          </div>
          {profile_badges}
        </div>
      <div class="stats">
        <div class="stat"><b>{summary.get("shared_bullish", 0)}</b><span>共同看多</span></div>
        <div class="stat"><b>{summary.get("divergent", 0)}</b><span>分歧</span></div>
        <div class="stat"><b>{summary.get("shared_tickers", 0)}</b><span>交集代號</span></div>
      </div>
      </div>
    </div>
    {sections}
  </main>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cname", default="xconviction.com", help="custom domain for GitHub Pages")
    args = ap.parse_args()

    profiles = profile_configs()
    run([sys.executable, "scripts/build_cross_profile_conviction.py"])
    cross_profile = load_json(CROSS_PROFILE_PATH)

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
    conviction_dir = DIST / "consensus"
    conviction_dir.mkdir(parents=True, exist_ok=True)
    copytree(ROOT / "assets", conviction_dir / "assets")
    (conviction_dir / "index.html").write_text(conviction_html(cross_profile), encoding="utf-8")
    if args.cname:
        (DIST / "CNAME").write_text(args.cname.strip() + "\n", encoding="utf-8")
    print(f"built {DIST}")


if __name__ == "__main__":
    raise SystemExit(main())
