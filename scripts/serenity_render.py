import json, datetime, sys, glob, os, re, html
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

SPLIT=1/3
def _argval(flag,default=None):
    a=sys.argv
    for i,x in enumerate(a):
        if x==flag and i+1<len(a): return a[i+1]
        if x.startswith(flag+'='): return x.split('=',1)[1]
    return default
# ---- DATA LAYER: read build_db output (db/stocks/*.json), fully self-contained ----
# Each per-stock JSON already carries company/industry/currency/price_series/price_status
# and mentions[] (date already ET-converted, stance, mention_type, reasons, url).
# No extracted.json / raw_tweets.json / meta.json needed; ETFs already excluded by build_db.
SCRIPT_DIR=Path(__file__).resolve().parent
ROOT=SCRIPT_DIR.parent
def _load_json(path, default):
    try:
        if Path(path).exists():
            return json.load(open(path, encoding='utf-8'))
    except Exception:
        pass
    return default
def _load_profile():
    raw=_argval('--profile') or os.environ.get('CONVICTION_PROFILE') or 'serenity'
    p=Path(raw)
    if not p.suffix:
        p=ROOT/'profiles'/f'{raw}.json'
    if not p.is_absolute():
        p=(ROOT/p).resolve()
    prof=_load_json(p,{})
    if not prof:
        prof={'slug':'serenity','display_name':'Serenity','handle':'aleabitoreddit','x_url':'https://x.com/aleabitoreddit','avatar':'assets/serenity-avatar.jpg','dashboard':{'output_prefix':'serenity-tracker','data_dir':'data/db'}}
    prof['_path']=str(p)
    prof.setdefault('slug','serenity')
    prof.setdefault('display_name','Serenity')
    prof.setdefault('handle','aleabitoreddit')
    prof.setdefault('x_url',f"https://x.com/{prof['handle']}")
    prof.setdefault('avatar','assets/serenity-avatar.jpg')
    prof.setdefault('dashboard',{})
    prof['dashboard'].setdefault('output_prefix',f"{prof['slug']}-tracker")
    prof['dashboard'].setdefault('data_dir','data/db')
    return prof
PROFILE=_load_profile()
P_DASH=PROFILE.get('dashboard') or {}
PROFILE_SLUG=PROFILE.get('slug','serenity')
PROFILE_NAME=PROFILE.get('display_name','Serenity')
PROFILE_HANDLE=(PROFILE.get('handle') or 'aleabitoreddit').lstrip('@')
PROFILE_X_URL=PROFILE.get('x_url') or f'https://x.com/{PROFILE_HANDLE}'
PROFILE_AVATAR=PROFILE.get('avatar') or 'assets/serenity-avatar.jpg'
PROFILE_OUTPUT_PREFIX=P_DASH.get('output_prefix') or f'{PROFILE_SLUG}-tracker'
_db_override=_argval('--db') or os.environ.get('CONVICTION_DB') or os.environ.get('SERENITY_DB')
DB=str(Path(_db_override).resolve()) if _db_override else str((ROOT/P_DASH.get('data_dir','data/db')).resolve())
STOCK={}                       # sym -> {company, industry, currency, price_series, price_status}
REPORTS={}                     # sym -> long-form ticker research report
allm=defaultdict(list)         # sym -> [(date, stance, mention_type, reason, url), ...] (all mentions)
MENT=defaultdict(list)         # sym -> [full mention dicts] (for the per-stock detail page)
_maxdate=None
_reports_dir=(ROOT/P_DASH.get('reports_dir','data/reports')).resolve()
for _rf in glob.glob(str(_reports_dir/'*.json')):
    try:
        _r=json.load(open(_rf,encoding='utf-8'))
        _sym=(_r.get('ticker') or '').upper()
        if _sym:
            REPORTS[_sym]=_r
    except Exception:
        pass
for _f in glob.glob(os.path.join(DB,'stocks','*.json')):
    _d=json.load(open(_f,encoding='utf-8')); s=_d['ticker']
    STOCK[s]={'company':_d.get('company'),'industry':_d.get('industry'),
              'exchange':_d.get('exchange') or 'US','price_symbol':_d.get('price_symbol') or s,
              'currency':_d.get('currency') or 'USD',
              'price_series':_d.get('price_series') or [],'price_status':_d.get('price_status')}
    for m in _d.get('mentions',[]):
        if not m.get('date'): continue
        dd=datetime.date.fromisoformat(m['date'])
        if _maxdate is None or dd>_maxdate: _maxdate=dd
        allm[s].append((dd,m.get('stance'),m.get('mention_type'),(m.get('reasons') or [None])[0],m.get('url') or ''))
        MENT[s].append({'tweet_id':m.get('tweet_id'),'date':m['date'],'stance':m.get('stance'),'mtype':m.get('mention_type'),
                        'reasons':m.get('reasons') or [],'is_risk':bool(m.get('is_risk')),
                        'text':m.get('text') or '','url':m.get('url') or '','eng':m.get('engagement') or {},
                        'text_may_be_truncated':m.get('text_may_be_truncated'),'media':m.get('media') or []})
REPORT_QUEUE=_load_json((ROOT/P_DASH.get('report_queue','data/report_queue.json')).resolve(),{})
REPORT_DECISIONS=_load_json((ROOT/P_DASH.get('report_decisions','data/report_decisions.json')).resolve(),{})
REPORT_FAILURES=_load_json((ROOT/P_DASH.get('report_failures','data/report_generation_failures.json')).resolve(),{})
REASON_TRANSLATIONS=_load_json((ROOT/P_DASH.get('reason_translations','data/reason_translations.json')).resolve(),{})

# as-of date: first positional CLI arg (YYYY-MM-DD), ignoring --flags and their values; else latest mention date
_skip=set()
for _i,_x in enumerate(sys.argv):
    if _x in ('--db','--lang','--profile') and _i+1<len(sys.argv): _skip.add(_i+1)
_pos=[a for _i,a in enumerate(sys.argv[1:],1) if not a.startswith('-') and _i not in _skip]
DAY=datetime.date.fromisoformat(_pos[0]) if _pos else (_maxdate or datetime.date.today())

def _update_stamp():
    try:
        mf=json.load(open(os.path.join(DB,'manifest.json'),encoding='utf-8'))
        raw=mf.get('generated_at')
        if raw:
            dt=datetime.datetime.fromisoformat(raw.replace('Z','+00:00'))
        else:
            dt=datetime.datetime.now(datetime.timezone.utc)
    except Exception:
        dt=datetime.datetime.now(datetime.timezone.utc)
    pt=dt.astimezone(ZoneInfo('America/Los_Angeles'))
    return pt.strftime('%Y-%m-%d %I:%M %p PT').replace(' 0',' ')

UPDATE_STAMP=_update_stamp()
TCO_AT_END_RE=re.compile(r'https?://t\.co/[A-Za-z0-9_]+\s*$')

def text_may_be_truncated(tx, stored_flag=None):
    if stored_flag is not None:
        return bool(stored_flag)
    tx=(tx or '').strip()
    return len(tx) >= 275 and bool(TCO_AT_END_RE.search(tx))

# ---- i18n: en/zh built-in; other languages loaded from SCRIPT_DIR/lang/{code}.json; default zh ----
LANG_ARG=_argval('--lang')
LANG=(LANG_ARG or 'zh').lower()
STR={
 'en':{
  'doc_title':"@aleabitoreddit — Serenity",'brand':"Serenity",
  'nav_day':"Daily",'nav_week':"Weekly",'nav_month':"Monthly",'nav_quarter':"Quarterly",'nav_reports':"Thesis",
  'disc_main':"Aggregation and tracking of public posts, summarized automatically by AI. It may contain errors or omissions and is not guaranteed accurate — always refer to the original posts and verify independently. This tracker does not constitute investment advice of any kind.",
  'disc_detail_top':"Stock detail · Aggregates the account's public posts only — not investment advice",
  'disc_chart':"Information aggregation only — not investment advice.",
  'q_methodology':"Methodology: bullish/bearish opinions the account expressed in posts (stances) — NOT actual holdings.",
  'stance_bull':"Bullish",'stance_bear':"Bearish",'stance_mixed':"Mixed",'stance_neutral':"Neutral",'stance_none':"No stance",
  'pfx_day':"today",'pfx_week':"this week",'pfx_month':"this month",'pfx_quarter':"this quarter",
  'badge_bull':"<i class='fa-solid fa-caret-up'></i> Bullish · {pfx}",'badge_bear':"<i class='fa-solid fa-caret-down'></i> Bearish · {pfx}",'badge_neutral':"<i class='fa-solid fa-circle'></i> Neutral · {pfx}",
  'badge_mixed':"<i class='fa-solid fa-rotate'></i> Mixed · {pfx}",'badge_none':"<i class='fa-regular fa-circle'></i> No stance · {pfx}",
  'surf_bear_n':"<i class='fa-solid fa-caret-down'></i> Bearish · {pfx} ({n})",'shift':"<i class='fa-solid fa-rotate'></i> Stance shift: {a} <i class='fa-solid fa-arrow-right'></i> {b}",
  'gain_lbl':"Gain",'chg_daily_lbl':"vs prior close",'gain_pending':"n/a",'count_unit':"",
  'tally_lbl':"Stance · {pfx}",'tally_bgonly':"No stance · {pfx} (background only)",'bgonly_inline':"Background mention only",
  'u_bull':"bull",'u_bear':"bear",'u_neu':"neu",
  'foot_first':"First mention {date}",'foot_first_last':"First mention {d1} · Latest {d2}",
  'updated':"<i class='fa-regular fa-clock'></i> Updated {date}",'detail_go':"Detail <i class='fa-solid fa-arrow-right'></i>",'detail':"Detail",
  'gain_tip':"From {fd} {px1} → to {ld} {px2}",
  'legend_stance_scroll':"| Stance = {pfx} stance; rolling window; counts are per-window",
  'subhd_notable':"<i class='fa-solid fa-chevron-down'></i> Notable {pfx} (bearish / stance shift)",'subhd_new':"<i class='fa-solid fa-chevron-down'></i> New {pfx}",
  'newc_line':"{n} first appeared {pfx} (tap for detail):",'subhd_rest':"<i class='fa-solid fa-chevron-down'></i> Other mentions",
  'restc_line':"{n} more mentioned {pfx}, ongoing or background (tap for detail):",'chips_more':"+{n} more <i class='fa-solid fa-chevron-down'></i>",
  'head_day_mentions':"Mentions today",'freq_7d':"7d",'freq_28d':"28d",
  'subhd_day':"Most-discussed today (by mentions today)",
  'head_week_mentions':"Mentions this week",'freq_near7':"last 7d",'freq_near28':"last 28d",
  'subhd_week':"Most-discussed this week (by mentions in last 7d)",
  'sec_count':"{range} · {ntk} names · {nment} mentions",'period_none':"No bearish or stance-shift names this period.",
  'head_month_mentions':"Mentions (28d)",'month_count':"28d · {ntk} names · {nment} mentions",
  'sec_count':"{range} · {ntk} names · {nment} mentions",'period_none':"No bearish or stance-shift names this period.",
  'subhd_month_top':"<i class='fa-solid fa-chevron-down'></i> Most-discussed this month (by 28d mentions) & stance mix",
  'subhd_month_new':"<i class='fa-solid fa-chevron-down'></i> New names this month (first appearance & >=5 mentions in 28d)",
  'trow_month_n':"{c} this month",
  'legend_new':"<i class='fa-solid fa-star'></i> New = first appeared this month",
  'legend_resurg':"<i class='fa-solid fa-arrow-trend-up'></i> Re-active = dormant name back this month (prior 28d ≤2, this month ≥5)",
  'legend_bar':"Bar = 28d stance mix (<b class='gb'><i class='fa-solid fa-caret-up'></i> bull</b> / <b class='gr'><i class='fa-solid fa-caret-down'></i> bear</b> / <i class='fa-solid fa-circle'></i> neu)",'tag_new':"<i class='fa-solid fa-star'></i> New",'tag_resurg':"<i class='fa-solid fa-arrow-trend-up'></i> Re-active",
  'quarter_count':"90d · {n} names · {v} mentions",
  'subhd_q_overview':"<i class='fa-solid fa-chevron-down'></i> Quarter direction (by # of names, not # of stances)",
  'q_net_bull':"Net-bullish names",'q_net_bear':"Net-bearish names",'q_balanced':"Balanced",'q_with_stance':"With stance",
  'q_summary':"By # of names: net-bullish <b class='gb'>{pbk}%</b> · net-bearish <b class='gr'>{prk}%</b> (of which {npure} bearish-only) | total stances — bull {TB} / bear {TR} / neutral {TN} (counts skew to a few high-frequency names, so direction is judged by # of names)",
  'subhd_q_table':"<i class='fa-solid fa-chevron-down'></i> All-names table (quarter)",
  'q_table_hint':"| Tap Gain / Mentions / Bull / Bear / Neutral headers to sort; ≥3 mentions in 90d ({n} names); blank industry (—) = unclassified",
  'th_ticker':"Ticker",'th_industry':"Industry",'th_first':"First mention",'th_last':"Latest mention",
  'th_gain':"Gain",'th_mentions':"Mentions",'th_bull':"Bull",'th_bear':"Bear",'th_neu':"Neutral",
  'gain_formula_tip':"Gain = (latest-mention price − first-mention price) ÷ first-mention price",
  'dd_back':"← Back",'dd_first_mention':"First mention",'dd_last_mention':"Latest mention",
  'dd_total':"Total mentions",'dd_first_px':"First price",'dd_today':"Today",
  'dd_reasons_bull':"Bull case",'dd_reasons_risk':"Risks mentioned",'dd_newest_first':"Newest first",
  'dd_no_bull':"(No explicit bull case)",'dd_no_risk':"(No risks mentioned)",'dd_no_detail':"No detail",
  'dd_all_posts':"All posts",'dd_posts_meta':"Reverse chronological · original language kept, tap to open",
  'dd_show_more':"show more on X",
  'post_initial':"Initial view",
  'chart_leg_bull':"Mentioned while bullish",'chart_leg_bear':"Mentioned while bearish",
  'chart_leg_note':"Dot = mention day (same-day merged); Y = closing price (non-trading days use last available close)",
  'chart_dot_tip':"{date} · mentioned ({stance}) · close {c}",
  'chart_ph_no_series':"No continuous price data (not covered) — mention timing only, no price curve",
  'chart_no_cover':"Price data not covered; limited chart.",
  'tag_background':"Background",'tag_comparison':"Analogy",'tag_quote':"Quote",'tag_mention':"Mention",
  'dd_ph_title':"No detail for {tk}",
  'dd_ph_body':"This name has only brief or background mentions — no expandable record yet.<br>Tap ← Back (top-right) to return.",
  'dd_view_all':"Show more posts ({n}) <i class='fa-solid fa-chevron-down'></i>",
  'dd_disc_body':"This page aggregates the account's public posts — stance, self-stated reasons, posting frequency, and the price path since first mention.",
  'disc_top':"⚠️ Aggregation and tracking of {link}'s public posts, summarized automatically by AI. <b>It may contain errors or omissions and is not guaranteed accurate — refer to the original posts and verify independently.</b> This tracker does not constitute investment advice.",
  'disc_top_sub':"Stance labels (bull / bear / neutral) are AI-inferred from the original text and may be inaccurate · No stance = mentioned only, no view expressed",
 },
 'zh':{
  'doc_title':"@aleabitoreddit — Serenity",'brand':"Serenity",
  'nav_day':"每日",'nav_week':"每週",'nav_month':"每月",'nav_quarter':"每季",'nav_reports':"投資論點",
  'disc_main':"公開貼文的整理與追蹤，由 AI 自動歸納，可能存在錯誤或遺漏；請以原文為準並自行核實。本追蹤不構成任何投資建議。",
  'disc_detail_top':"個股詳情 · 僅整理 Serenity 的公開貼文，不構成投資建議",
  'disc_chart':"僅供資訊整理，不構成投資建議。",
  'q_methodology':"統計口徑：Serenity 在貼文中表達的看多 / 看空觀點，並非實際持倉。",
  'stance_bull':"看多",'stance_bear':"看空",'stance_mixed':"多空並存",'stance_neutral':"中性",'stance_none':"未表態",
  'pfx_day':"今日",'pfx_week':"本週",'pfx_month':"近 28 日",'pfx_quarter':"近 90 日",
  'badge_bull':"<i class='fa-solid fa-caret-up'></i> {pfx}看多",'badge_bear':"<i class='fa-solid fa-caret-down'></i> {pfx}看空",'badge_neutral':"<i class='fa-solid fa-circle'></i> {pfx}中性",
  'badge_mixed':"<i class='fa-solid fa-rotate'></i> {pfx}多空並存",'badge_none':"<i class='fa-regular fa-circle'></i> {pfx}未表態",
  'surf_bear_n':"<i class='fa-solid fa-caret-down'></i> {pfx}看空（{n} 則）",'shift':"<i class='fa-solid fa-rotate'></i> 較上次表態：{a} <i class='fa-solid fa-arrow-right'></i> {b}",
  'gain_lbl':"漲幅",'chg_daily_lbl':"較前收",'gain_pending':"暫無資料",'count_unit':"次",
  'tally_lbl':"{pfx}立場",'tally_bgonly':"{pfx}立場：未表態（僅背景提及）",'bgonly_inline':"僅作為背景提及，未表態",
  'u_bull':"多",'u_bear':"空",'u_neu':"中",
  'foot_first':"首次提及 {date}",'foot_first_last':"首次提及 {d1} · 最近 {d2}",
  'updated':"<i class='fa-regular fa-clock'></i> 更新 {date}",'detail_go':"詳情 <i class='fa-solid fa-arrow-right'></i>",'detail':"詳情",
  'gain_tip':"起 {fd} {px1} → 止 {ld} {px2}",
  'legend_stance_scroll':"| 立場 = {pfx}表態；滾動視窗；次數為該視窗內計數",
  'subhd_notable':"<i class='fa-solid fa-chevron-down'></i> {pfx}值得注意（看空 / 立場轉變）",'subhd_new':"<i class='fa-solid fa-chevron-down'></i> {pfx}新出現的標的",
  'newc_line':"{pfx}首次進入視野 {n} 檔（可點進詳情）：",'subhd_rest':"<i class='fa-solid fa-chevron-down'></i> 其他提及",
  'restc_line':"{pfx}另外提到 {n} 檔，屬於既有關注或背景提及（可點進詳情）：",'chips_more':"展開剩餘 {n} 檔 <i class='fa-solid fa-chevron-down'></i>",
  'head_day_mentions':"今日提及",'freq_7d':"近 7 日",'freq_28d':"近 28 日",
  'subhd_day':"今日討論最多的標的（按今日提及次數）",
  'head_week_mentions':"本週提及",'freq_near7':"近 7 日",'freq_near28':"近 28 日",
  'subhd_week':"本週討論最多的標的（按近 7 日提及次數）",
  'sec_count':"{range} · {ntk} 檔標的 · {nment} 次提及",'period_none':"本期沒有看空或立場轉變的標的。",
  'head_month_mentions':"近 28 日提及",'month_count':"近 28 日 · {ntk} 檔標的 · {nment} 次提及",
  'subhd_month_top':"<i class='fa-solid fa-chevron-down'></i> 本月討論最多的標的（按近 28 日提及次數）與立場分布",
  'subhd_month_new':"<i class='fa-solid fa-chevron-down'></i> 本月新增標的（首次進入視野且近 28 日 >= 5 次）",
  'trow_month_n':"本月 {c} 次",
  'legend_new':"<i class='fa-solid fa-star'></i> 新增 = 本月首次進入視野",
  'legend_resurg':"<i class='fa-solid fa-arrow-trend-up'></i> 重新活躍 = 老標的沉寂後本月重新放量（前 28 天 ≤ 2 次、本月 ≥ 5 次）",
  'legend_bar':"條形 = 近 28 日立場分布（<b class='gb'><i class='fa-solid fa-caret-up'></i> 多</b> / <b class='gr'><i class='fa-solid fa-caret-down'></i> 空</b> / <i class='fa-solid fa-circle'></i> 中）",'tag_new':"<i class='fa-solid fa-star'></i> 新增",'tag_resurg':"<i class='fa-solid fa-arrow-trend-up'></i> 重新活躍",
  'quarter_count':"近 90 日 · {n} 檔標的 · {v} 次提及",
  'subhd_q_overview':"<i class='fa-solid fa-chevron-down'></i> 季度方向總覽（按標的數，不按表態次數）",
  'q_net_bull':"看多",'q_net_bear':"看空",'q_balanced':"持平",'q_with_stance':"有表態",
  'q_summary':"按標的數：淨看多 <b class='gb'>{pbk}%</b> · 淨看空 <b class='gr'>{prk}%</b>（其中純看空 {npure} 檔）　| 累計表態次數：看多 {TB} / 看空 {TR} / 中性 {TN}",
  'subhd_q_table':"<i class='fa-solid fa-chevron-down'></i> 季度全標的表",
  'q_table_hint':"| 點選 漲幅 / 提及次數 / 看多 / 看空 / 中性 欄位可排序；近 90 日 ≥ 3 次提及（{n} 檔）；產業空白（—）= 未分類",
  'th_ticker':"代號",'th_industry':"產業",'th_first':"首次提及",'th_last':"最近提及",
  'th_gain':"漲幅",'th_mentions':"提及次數",'th_bull':"看多",'th_bear':"看空",'th_neu':"中性",
  'gain_formula_tip':"漲幅 =（最近提及價 − 首次提及價）÷ 首次提及價",
  'dd_back':"← 返回",'dd_first_mention':"首次提及",'dd_last_mention':"最近提及",
  'dd_total':"總提及",'dd_first_px':"首次提及價格",'dd_today':"今日",
  'dd_reasons_bull':"看多理由",'dd_reasons_risk':"提到的風險",'dd_newest_first':"最新在前",
  'dd_no_bull':"（暫無明確看多理由）",'dd_no_risk':"暫未提及風險",'dd_no_detail':"暫無詳情",
  'dd_all_posts':"全部貼文",'dd_posts_meta':"按時間倒序 · 原文保留英文，點擊跳原帖",
  'dd_show_more':"在 X 查看更多",
  'post_initial':"初始觀點",
  'chart_leg_bull':"看多時提及",'chart_leg_bear':"看空時提及",
  'chart_leg_note':"圓點 = 提及當天（同日合併）；縱軸 = 收盤價（非交易日使用最近交易日收盤價）",
  'chart_dot_tip':"{date} · {stance}時提及 · 收盤 {c}",
  'chart_ph_no_series':"無連續價格資料（行情未覆蓋）— 僅記錄提及時間點，不繪製價格曲線",
  'chart_no_cover':"該標的行情未覆蓋，價格曲線有限。",
  'tag_background':"背景",'tag_comparison':"類比",'tag_quote':"引用",'tag_mention':"提及",
  'dd_ph_title':"暫無 {tk} 的詳情",
  'dd_ph_body':"該標的僅少量或背景提及，尚未形成可展開的記錄。<br>點擊右上角「← 返回」回到看板。",
  'dd_view_all':"查看更多貼文（剩餘 {n} 則）<i class='fa-solid fa-chevron-down'></i>",
  'dd_disc_body':"本頁整理的是 Serenity 的公開貼文：立場、自述理由、發文頻率，以及自首次提及以來的價格走勢。",
  'disc_top':"⚠️ 本頁為對 {link} 公開貼文的整理與追蹤，由 AI 自動歸納，<b>可能存在錯誤或遺漏；請以原文為準並自行核實</b>。本追蹤不構成任何投資建議。",
  'disc_top_sub':"立場標籤（看多 / 看空 / 中性）由 AI 根據原文語意推斷，可能存在誤判 · 未表態 = 僅提及，未表達方向",
 },
}
def _load_lang(code):
    if code in STR: return STR[code]
    f=SCRIPT_DIR/'lang'/(code+'.json')
    if f.exists():
        try: return json.load(open(f,encoding='utf-8'))
        except Exception: return None
    return None
_EN=STR['en']; _L=_load_lang(LANG) or _EN
def t(key,**kw):
    s=_L.get(key)
    if s is None: s=_EN.get(key)
    if s is None: s=key
    return s.format(**kw) if kw else s

# windowed views as-of DAY (a board dated DAY only knows mentions on/before DAY)
exp=defaultdict(list); mdates=defaultdict(list)
for s,ms in allm.items():
    for d,st,mt,r,u in ms:
        if d>DAY: continue
        mdates[s].append(d)
        if mt=='explicit_stance':
            exp[s].append((d,st,r,u))

def cnt(s,w0,w1): return sum(1 for d in mdates[s] if w0<=d<=w1)
def total(s): return len(mdates[s])
def first(s): return min(mdates[s]) if mdates[s] else None
def last(s): return max(mdates[s]) if mdates[s] else None
def win_exp(s,w0,w1):
    eb=er=en=0
    for d,st,_,_ in exp[s]:
        if w0<=d<=w1:
            if st=='bullish':eb+=1
            elif st=='bearish':er+=1
            else:en+=1
    return eb,er,en
def badge(eb,er,en,pfx):
    if eb==0 and er==0 and en==0:return 'none',t('badge_none',pfx=pfx)
    if eb==0 and er==0:return 'neu',t('badge_neutral',pfx=pfx)
    tot=eb+er;mino=min(eb,er)
    if mino>0 and mino/tot>=SPLIT:return 'shift',t('badge_mixed',pfx=pfx)
    return ('bull',t('badge_bull',pfx=pfx)) if eb>er else ('bear',t('badge_bear',pfx=pfx))
def prior_dir(s,before):
    days=defaultdict(lambda:[0,0])
    for d,st,_,_ in exp[s]:
        if d<before:
            if st=='bullish':days[d][0]+=1
            elif st=='bearish':days[d][1]+=1
    for d in sorted(days,reverse=True):
        eb,er=days[d]
        if eb>er and eb>0:return 'bull'
        if er>eb and er>0:return 'bear'
    return None
def cur_of(s):
    c=STOCK.get(s,{}).get('currency','USD');return c if c!='USD' else ''
def market_of(s):
    d=STOCK.get(s,{})
    ex=(d.get('exchange') or '').lower()
    cur=(d.get('currency') or 'USD').upper()
    ps=(d.get('price_symbol') or s).upper()
    if 'otc' in ex or ps.endswith('F') and cur=='USD':
        return 'OTC'
    if cur=='USD' and (not ex or ex=='us' or 'nasdaq' in ex or 'nyse' in ex or 'amex' in ex):
        return 'US'
    if cur in ('SEK','EUR','GBP','CHF','DKK','NOK') or any(x in ex for x in ('stockholm','london','paris','xetra','swiss','oslo','copenhagen','helsinki','milan','amsterdam','europe')):
        return 'EU'
    if cur in ('JPY',) or 'tokyo' in ex or ps.endswith('.T'):
        return 'JP'
    if cur in ('KRW',) or 'korea' in ex or ps.endswith('.KS') or ps.endswith('.KQ'):
        return 'KR'
    if cur in ('HKD',) or 'hong kong' in ex or ps.endswith('.HK'):
        return 'HK'
    if cur in ('CAD',) or 'toronto' in ex or ps.endswith('.TO') or ps.endswith('.V'):
        return 'CA'
    if cur in ('AUD',) or 'asx' in ex or ps.endswith('.AX'):
        return 'AU'
    if cur in ('TWD',) or 'taiwan' in ex or ps.endswith('.TW'):
        return 'TW'
    if cur in ('CNY','CNH') or 'china' in ex:
        return 'CN'
    return cur or 'Other'
def market_pill(s):
    return f'<span class="market">{market_of(s)}</span>'
def theme_of(s):
    d=STOCK.get(s,{})
    hay=' '.join(str(x or '') for x in (s,d.get('company'),d.get('industry'))).lower()
    if any(x in hay for x in ('hbm','memory','dram','nand','sandisk','sk hynix','micron','samsung')):
        return 'HBM'
    if any(x in hay for x in ('inp substrate','axt inc','axti')):
        return 'InP substrates'
    if any(x in hay for x in ('cpo','photonic','optical','laser','lightwave','poet','lumentum','coherent','applied optoelectronics','jabil')):
        return 'CPO'
    if any(x in hay for x in ('power','grid','nuclear','utility','utilities','energy storage','electrical')):
        return 'Power'
    if any(x in hay for x in ('cooling','thermal','liquid cooling','ai servers','super micro','vertiv')):
        return 'Cooling'
    if any(x in hay for x in ('networking','interconnect','connectivity','pcie','cxl','aec','ethernet','switch','broadcom','marvell','credo','astera')):
        return 'Networking'
    if any(x in hay for x in ('ai cloud','gpu cloud','neocloud','datacenter','data center','hyperscaler','bitcoin miner','oci','oracle','coreweave','nebius','iren','wulf','cipher')):
        return 'AI cloud'
    if any(x in hay for x in ('ai chip','gpu','asic','custom silicon','semiconductor foundry','wafer foundry','cpu','foundry','semis','nvidia','amd','tsmc','intel','globalfoundries','tower semiconductor')):
        return 'Custom silicon'
    return 'Other'
def theme_pill(s):
    th=theme_of(s)
    cls='other' if th=='Other' else ''
    return f'<span class="theme {cls}">{th}</span>'
def report_update_pill(s):
    ups=(REPORTS.get(s) or {}).get('updates') or []
    if not ups: return ''
    raw=ups[0].get('date') or ''
    d=raw[5:] or 'new'
    fresh=''
    try:
        if (DAY-datetime.date.fromisoformat(raw)).days<=3:
            fresh=' fresh'
    except Exception:
        pass
    return f'<span class="updchip{fresh}"><i class="fa-solid fa-file-lines"></i> 論點更新 {d}</span>'
def ymd(d):return d.strftime('%Y-%m-%d') if d else '—'
def co_of(s):return STOCK.get(s,{}).get('company') or s
def ind_of(s):return STOCK.get(s,{}).get('industry') or ''
INDUSTRY_ZH={
    'Optical Modules':'光通訊模組',
    'Optical Comms':'光通訊',
    'AI Cloud/GPU':'AI 雲端 / GPU',
    'AI Photonics/CPO Lasers':'AI 光子學 / CPO 雷射',
    'InP Substrates':'磷化銦基板',
    'AI Chips':'AI 晶片',
    'Hyperscaler':'超大規模雲端服務商',
    'SOI Wafers':'SOI 晶圓',
    'Wafer Foundry':'晶圓代工',
    'Compound Semiconductors':'化合物半導體',
}
def ind_label(s):
    ind=ind_of(s)
    if not ind:return ''
    if LANG=='zh' and ind in INDUSTRY_ZH:return f'{INDUSTRY_ZH[ind]} ({ind})'
    return ind
BCLASS={'bull':'bull','bear':'bear','shift':'cw','neu':'neutral','none':'neutral'}
def distbar_html(eb,er,en):
    tot=eb+er+en
    def seg(cls,v):
        w=0 if tot==0 else round(v/tot*100)
        mw=';min-width:4px' if v>0 else ''
        return f'<i class="{cls}" style="width:{w}%{mw}"></i>'
    bar=f'<div class="distbar">{seg("b",eb)}{seg("r",er)}{seg("n",en)}</div>'
    num=f'<span class="distnum"><b class="gb">{eb}</b> {t("u_bull")} <b class="gr">{er}</b> {t("u_bear")} {en} {t("u_neu")}</span>'
    return bar,num

# ---------- per-stock DETAIL PAGE data (computed from MENT/price_series, as-of DAY) ----------
def _close_on_before(ser,d):
    cl=None
    for p in ser:
        if datetime.date.fromisoformat(p['date'])<=d: cl=p.get('close')
        else: break
    return cl
def _close_on_after(ser,d):
    for p in ser:
        pd=datetime.date.fromisoformat(p['date'])
        if pd>=d: return p.get('close'),pd
    return None,None
def first_px(s):
    ser=STOCK.get(s,{}).get('price_series') or []
    if not ser or not first(s): return None
    c,_=_close_on_after(ser,first(s)); return c
def last_px(s):
    ser=STOCK.get(s,{}).get('price_series') or []
    if not ser or not last(s): return None
    return _close_on_before(ser,last(s))
def pxcell(px,s):
    if px is None: return '<span class="qpx">—</span>'
    cur=cur_of(s); return f'<span class="qpx">{(cur+" ") if cur else ""}{px:g}</span>'
def pxtxt(px,s):
    if px is None: return '—'
    cur=cur_of(s); return f'{(cur+" ") if cur else ""}{px:g}'
def mention_pct(s):
    # 季报口径:首提价 → 最近提及价(两个已展示的价格之间的变化),不取"至今"
    f=first_px(s); l=last_px(s)
    return (l-f)/f*100 if (f and l and f>0) else None
def mention_chg(s):
    pct=mention_pct(s)
    if pct is None: return f'<span class="chg pending">{t("gain_pending")}</span>'
    cls='up' if pct>=0 else 'down'; sign='+' if pct>=0 else ''
    return f'<span class="chg {cls}">{sign}{pct:.1f}%</span>'
def daily_pct(s):
    # 日报口径:较上一交易日(截至报告日的最新两根收盘)
    ser=[p for p in (STOCK.get(s,{}).get('price_series') or []) if datetime.date.fromisoformat(p['date'])<=DAY]
    if len(ser)>=2:
        a=ser[-2].get('close'); b=ser[-1].get('close')
        if a and b and a>0: return (b-a)/a*100
    return None
def daily_chg(s):
    pct=daily_pct(s)
    if pct is None: return f'<span class="chg pending">{t("gain_pending")}</span>'
    cls='up' if pct>=0 else 'down'; sign='+' if pct>=0 else ''
    return f'<span class="chg {cls}">{sign}{pct:.1f}%</span>'
def chg_tip(s):
    # A 方案:显示两个收盘价“实际所在交易日”(可能因数据滞后早于提及日)
    ser=STOCK.get(s,{}).get('price_series') or []
    f0=first(s); l0=last(s)
    if not ser or not f0 or not l0: return ''
    fp,fd=_close_on_after(ser,f0)
    lp=None; ld=None
    for p in ser:
        if datetime.date.fromisoformat(p['date'])<=l0: lp=p.get('close'); ld=p['date']
        else: break
    if fp is None or lp is None or fd is None or not ld: return ''
    return t('gain_tip', fd=fd.isoformat(), px1=pxtxt(fp,s), ld=ld, px2=pxtxt(lp,s))
def chg_info(s):
    tip=chg_tip(s)
    return f' <span class="qinfo" data-tip="{tip}" onclick="event.stopPropagation()"><i class="fa-regular fa-circle-question"></i></span>' if tip else ''
def dd_data():
    STXT={'bull':t('stance_bull'),'bear':t('stance_bear'),'shift':t('stance_mixed'),'neutral':t('stance_neutral'),'none':t('stance_none')}
    out={}
    for s in mdates:
        if not mdates[s]: continue
        if cnt(s,DAY-datetime.timedelta(days=89),DAY) < 3 and cnt(s,DAY-datetime.timedelta(days=27),DAY) < 1: continue   # 不在板上(day/week/month/quarter 窗口外)→ 不可点
        if total(s) < 1: continue   # 无任何提及 → 跳过
        ms=[m for m in MENT[s] if datetime.date.fromisoformat(m['date'])<=DAY]
        if not ms: continue
        ms.sort(key=lambda m:m['date'])                       # ascending
        eb=er=en=0
        for m in ms:
            if m['mtype']=='explicit_stance':
                if m['stance']=='bullish': eb+=1
                elif m['stance']=='bearish': er+=1
                else: en+=1
        bk,_=badge(eb,er,en,'')
        stance={'bull':'bull','bear':'bear','shift':'shift','neu':'neutral','none':'none'}[bk]
        # price
        d0=STOCK.get(s,{}); ser=[p for p in (d0.get('price_series') or []) if datetime.date.fromisoformat(p['date'])<=DAY]
        okp = d0.get('price_status') in ('ok','partial') and len(ser)>=2
        fdate=first(s)
        basePx=baseDate=None
        if okp and fdate: basePx,baseDate=_close_on_after(ser,fdate)
        lastPx=ser[-1]['close'] if ser else None
        gain=(lastPx-basePx)/basePx*100 if (basePx and lastPx and basePx>0) else None
        series=[{'d':p['date'],'c':p['close']} for p in ser] if okp else []
        # one dot per distinct explicit-stance day (color = that day's net stance)
        daymap={}
        for m in ms:
            if m['mtype']!='explicit_stance': continue
            daymap.setdefault(m['date'],[0,0])
            if m['stance']=='bullish': daymap[m['date']][0]+=1
            elif m['stance']=='bearish': daymap[m['date']][1]+=1
        dots=[]
        if okp:
            for dy,(b,r) in sorted(daymap.items()):
                st='bull' if b>r else ('bear' if r>b else 'neu')
                cl=_close_on_before(ser,datetime.date.fromisoformat(dy))
                dots.append({'d':dy,'c':(cl if cl is not None else ser[0]['close']),'s':st})
        # horizons from first mention
        # reasons (newest-first, exact-dedup, top N), split by is_risk
        def risk_reason_text(r):
            hay=(r or '').lower()
            terms=('risk','debt','interest','dilution','atm','pressure','sell','selling','bear','bearish',
                   'unlock','damaging','hurt','hurts','dragged','stagnant','correlation','bitcoin exposure',
                   'liquidity','multi-sourcing','delayed','execution','concern','too high','not hold',
                   'red flag','exposure','contagion','bubble','bubbles','eaten alive','regulating away',
                   'lower supply','gov','government','share increase','refining','precursors',
                   'uncertain','lack','lacks','would lack','export controlled','capacity issues',
                   'potential issues','priced in','premium','overextended')
            return any(t in hay for t in terms)
        def collect(want_risk,want_stance,capn):
            seen=set(); res=[]
            for m in reversed(ms):
                if m['mtype']!='explicit_stance': continue
                if want_risk is not None and m['is_risk']!=want_risk: continue
                if want_stance and m['stance']!=want_stance: continue
                for r in (m['reasons'] or []):
                    k=(r or '').strip().lower()
                    if not k or k in seen: continue
                    if want_risk and not risk_reason_text(r): continue
                    seen.add(k); res.append([r,m['url'],m['date']])
                    if len(res)>=capn: return res
            return res
        reasonsBull=collect(False,'bullish',6)
        reasonsRisk=collect(True,None,4)
        # posts: ALL as-of DAY, newest-first; preserve original tweet spacing for readability.
        TAG={'background':t('tag_background'),'comparison':t('tag_comparison'),'quote_or_other':t('tag_quote')}
        posts=[]
        for m in reversed(ms):
            if m['mtype']=='explicit_stance':
                tag={'bullish':t('stance_bull'),'bearish':t('stance_bear'),'neutral':t('stance_neutral')}.get(m['stance'],t('stance_neutral')); st=m['stance']
            else:
                tag=TAG.get(m['mtype'],t('tag_mention')); st='meta'
            posts.append({'id':m.get('tweet_id'),'d':m['date'],'tag':tag,'st':st,'text':m['text'],'url':m['url'],
                          'cut':text_may_be_truncated(m['text'],m.get('text_may_be_truncated')),
                          'media':m.get('media') or []})
        if posts: posts[-1]['first']=True            # 最早一条 = 初始观点
        out[s]={'co':co_of(s),'industry':ind_of(s),'market':market_of(s),'theme':theme_of(s),'otc':(not okp),'stance':stance,'stanceTxt':STXT.get(stance,'—'),
                'first':ymd(fdate),'last':ymd(last(s)),'total':total(s),'bull':eb,'bear':er,'neu':en,
                'm_today':cnt(s,DAY,DAY),'m7':cnt(s,DAY-datetime.timedelta(days=6),DAY),'m28':cnt(s,DAY-datetime.timedelta(days=27),DAY),
                'firstPx':(f'{basePx:g}' if basePx else None),'cur':cur_of(s),
                'gain':((('+' if gain>=0 else '')+f'{gain:.1f}%') if gain is not None else None),
                'series':series,'dots':dots,
                'reasonsBull':reasonsBull,'reasonsRisk':reasonsRisk,
                'posts':posts,'report':REPORTS.get(s)}
    return out

def _freqline(s, freq, w1):
    parts=[]
    for lbl,kind in freq:
        if kind=='w7': v=cnt(s,w1-datetime.timedelta(days=6),w1)
        elif kind=='w28': v=cnt(s,w1-datetime.timedelta(days=27),w1)
        elif kind=='total': v=total(s)
        else: continue
        parts.append(f'{lbl} <b>{v}</b>')
    return ' · '.join(parts)
def bigcard(s, w0, w1, pfx, head_lbl, freq, chg_kind):
    c=cnt(s,w0,w1); eb,er,en=win_exp(s,w0,w1); bk,bl=badge(eb,er,en,pfx); cls=BCLASS[bk]
    curh=market_pill(s)+theme_pill(s)+report_update_pill(s)
    chglbl=t('chg_daily_lbl') if chg_kind=='daily' else t('gain_lbl')
    chg_fn=daily_chg if chg_kind=='daily' else mention_chg
    info=chg_info(s) if chg_kind=='mention' else ''
    if bk=='none':
        tally=f'<span class="dlbl">{t("tally_bgonly",pfx=pfx)}</span>'
    else:
        tally=(f'<span class="dlbl">{t("tally_lbl",pfx=pfx)}</span><span class="dtally">'
          f'<b class="gb">{eb}</b><span class="u">{t("u_bull")}</span> <b class="gr">{er}</b><span class="u">{t("u_bear")}</span> <b>{en}</b><span class="u">{t("u_neu")}</span></span>')
    foot=t('foot_first',date=ymd(first(s))) if chg_kind=='daily' else t('foot_first_last',d1=ymd(first(s)),d2=ymd(last(s)))
    fl=_freqline(s,freq,w1)
    cfreq=f'<span class="cfreq">· {fl}</span>' if fl else ''
    return (f'<div class="card big {cls}" onclick="dd(\'{s}\')">'
      f'<div class="ch"><div class="cid"><span class="tk">{s}</span>{curh}'
      f'<span class="hchg"><span class="hchg-lbl">{chglbl}</span> {chg_fn(s)}{info}</span></div>'
      f'<div class="badge {cls}">{bl}</div></div>'
      f'<div class="countline"><span class="tlbl">{head_lbl}</span><span class="tbig">{c}</span><span class="tunit">{t("count_unit")}</span>{cfreq}</div>'
      f'<div class="distrow">{tally}</div>'
      f'<div class="cfoot"><span>{foot}</span><span class="go">{t("detail_go")}</span></div></div>')

def period_section(cfg):
    sid=cfg['id']; pfx=cfg['pfx']; w0,w1=cfg['win']; BIG=cfg['big']
    head_lbl=cfg['head']; freq=cfg['freq']
    chg_fn=daily_chg if cfg.get('chg')=='daily' else mention_chg
    syms=[s for s in mdates if cnt(s,w0,w1)>0]
    big=sorted([s for s in syms if cnt(s,w0,w1)>=BIG], key=lambda s:-cnt(s,w0,w1))
    if len(big)<3 and len(syms)>len(big):
        rest=sorted([s for s in syms if s not in set(big)], key=lambda s:-cnt(s,w0,w1))
        big=big+rest[:3-len(big)]
    small=[s for s in syms if s not in set(big)]
    def freqline_plain(s):
        parts=[]
        for lbl,kind in freq:
            if kind=='w7': v=cnt(s,w1-datetime.timedelta(days=6),w1)
            elif kind=='w28': v=cnt(s,w1-datetime.timedelta(days=27),w1)
            elif kind=='total': v=total(s)
            parts.append(f'{lbl} {v}')
        return ' · '.join(parts)
    rows=[]; newc=[]; restc=[]
    for s in small:
        c=cnt(s,w0,w1); eb,er,en=win_exp(s,w0,w1); tags=[]
        if er>0: tags.append(('bear',t('surf_bear_n',pfx=pfx,n=er)))
        tot=eb+er;mino=min(eb,er);tdir='bull' if eb>er and eb>0 else('bear' if er>eb and er>0 else None)
        if mino>0 and tot>0 and mino/tot>=SPLIT: tags.append(('cw',t('badge_mixed',pfx=pfx)))
        else:
            ld=prior_dir(s,w0)
            if tdir and ld and tdir!=ld: mp={'bull':t('stance_bull'),'bear':t('stance_bear')};tags.append(('cw',t('shift',a=mp[ld],b=mp[tdir])))
        if tags: rows.append((s,c,tags))
        elif first(s) is not None and first(s)>=w0: newc.append((s,c))
        else: restc.append((s,c))
    rows.sort(key=lambda x:-x[1])
    def srow(s,c,tags):
        chips=' '.join(f'<span class="stag {k}">{tg}</span>' for k,tg in tags)
        return (f'<div class="surfrow" onclick="dd(\'{s}\')"><span class="tk">{s}</span>{market_pill(s)}{theme_pill(s)}{report_update_pill(s)}<span class="sco2">{co_of(s)}</span>{chips}'
          f'<span class="rrt">{chg_fn(s)}{chg_info(s) if cfg.get("chg")=="mention" else ""}<span class="sfreq">{pfx} {c} · {freqline_plain(s)}</span><span class="go">{t("detail_go")}</span></span></div>')
    def chips(lst): return ' '.join(f'<span class="rchip" onclick="dd(\'{s}\')">{s} <em>{market_of(s)}</em> <em>{theme_of(s)}</em>{report_update_pill(s)} · {c}</span>' for s,c in sorted(lst,key=lambda x:-x[1]))
    def chips_collapsed(lst):
        items=sorted(lst,key=lambda x:-x[1]); N=14
        mk=lambda pairs:' '.join(f'<span class="rchip" onclick="dd(\'{s}\')">{s} <em>{market_of(s)}</em> <em>{theme_of(s)}</em>{report_update_pill(s)} · {c}</span>' for s,c in pairs)
        if len(items)<=N: return mk(items)
        gid=f'rest_{sid}'
        return (f'{mk(items[:N])} <span id="{gid}" style="display:none">{mk(items[N:])}</span>'
          f'<span class="morechip" onclick="event.stopPropagation();var e=document.getElementById(\'{gid}\');e.style.display=\'inline\';this.style.display=\'none\'">{t("chips_more",n=len(items)-N)}</span>')
    ntk=len(syms); nment=sum(cnt(s,w0,w1) for s in syms)
    rowhtml='\n'.join(srow(s,c,tg) for s,c,tg in rows) or f'<div class="cbox">{t("period_none")}</div>'
    return f'''<section id="{sid}" class="period-sec">
<div class="sec"><div class="sechd"><div class="st">{cfg['title']}</div><div class="datepill">{cfg['pill']}</div>
<div class="sn"><span class="cnt">{t('sec_count',range=cfg['range'],ntk=ntk,nment=nment)}</span><span class="upd">{t('updated',date=UPDATE_STAMP)}</span></div></div>
<div class="subhd"><i class="fa-solid fa-chevron-down"></i> {cfg['subhd']}</div></div>
<div class="wall">{''.join(bigcard(s, w0, w1, pfx, head_lbl, freq, cfg.get('chg')) for s in big)}</div>
<div class="daypad">
<div class="subhd" style="margin-top:20px">{t('subhd_notable',pfx=pfx)}</div>
{rowhtml}
<div class="subhd" style="margin-top:18px">{t('subhd_new',pfx=pfx)}</div>
<div class="cbox">{t('newc_line',pfx=pfx,n=f'<b>{len(newc)}</b>')}<br>{chips(newc)}</div>
<div class="subhd" style="margin-top:4px">{t('subhd_rest')}</div>
<div class="cbox">{t('restc_line',pfx=pfx,n=f'<b>{len(restc)}</b>')}<br>{chips_collapsed(restc)}</div>
</div><div style="height:40px"></div></section>'''

def month_section():
    M0=DAY-datetime.timedelta(days=27); P0=M0-datetime.timedelta(days=28)
    syms=[s for s in mdates if cnt(s,M0,DAY)>0]
    def is_new(s): return first(s) and first(s)>=M0
    def is_resurg(s): return first(s) and first(s)<M0 and cnt(s,P0,M0-datetime.timedelta(days=1))<=2 and cnt(s,M0,DAY)>=5
    newcards=sorted([s for s in syms if is_new(s) and cnt(s,M0,DAY)>=5], key=lambda s:-cnt(s,M0,DAY))
    top=sorted(syms,key=lambda s:-cnt(s,M0,DAY))[:10]
    def mtag(s):
        if is_new(s): return f'<span class="mtag new">{t("tag_new")}</span>'
        if is_resurg(s): return f'<span class="mtag act">{t("tag_resurg")}</span>'
        return ''
    def trow(i,s):
        c=cnt(s,M0,DAY);eb,er,en=win_exp(s,M0,DAY)
        if eb+er+en==0:
            mid=f'<span class="bgonly">{t("bgonly_inline")}</span><span></span>'
        else:
            bar,num=distbar_html(eb,er,en); mid=f'{num}{bar}'
        return (f'<div class="trow" onclick="dd(\'{s}\')">'
          f'<span class="trk">{i}</span><span class="ttag">{mtag(s)}</span><span class="ttk">{s}{market_pill(s)}{theme_pill(s)}{report_update_pill(s)}</span>'
          f'{mid}<span class="tn2">{t("trow_month_n",c=f"<b>{c}</b>")}</span>'
          f'<span class="tchg">{t("gain_lbl")} {mention_chg(s)}{chg_info(s)}</span><span class="sgo">{t("detail")}</span></div>')
    ntk=len(syms); nment=sum(cnt(s,M0,DAY) for s in syms)
    legparts=[]
    if any(is_new(s) for s in top): legparts.append(t('legend_new'))
    if any(is_resurg(s) for s in top): legparts.append(t('legend_resurg'))
    legparts.append(t('legend_bar'))
    LEG=f'<div class="leg">{"　·　".join(legparts)}</div>'
    return f'''<section id="month" class="period-sec">
<div class="sec"><div class="sechd"><div class="st">{t('nav_month')}</div><div class="datepill">{M0.strftime("%Y-%m-%d")} ~ {DAY.strftime("%m-%d")}</div>
<div class="sn"><span class="cnt">{t('month_count',ntk=ntk,nment=nment)}</span><span class="upd">{t('updated',date=UPDATE_STAMP)}</span></div></div>
<div class="subhd">{t('subhd_month_top')}</div></div>
<div class="daypad">
<div class="toplist-wrap"><div class="toplist">{''.join(trow(i,s) for i,s in enumerate(top,1))}</div>{LEG}</div>
<div class="subhd" style="margin-top:26px">{t('subhd_month_new')}</div>
<div class="mwall">{''.join(bigcard(s, M0, DAY, t('pfx_month'), t('head_month_mentions'), [], 'mention') for s in newcards)}</div>
</div><div style="height:40px"></div></section>'''

def quarter_section():
    Q0=DAY-datetime.timedelta(days=89)
    syms=[s for s in mdates if cnt(s,Q0,DAY)>0]; all_v=sum(cnt(s,Q0,DAY) for s in syms)
    we={s:win_exp(s,Q0,DAY) for s in syms}
    TB=sum(we[s][0] for s in syms); TR=sum(we[s][1] for s in syms); TN=sum(we[s][2] for s in syms)
    # 按标的数(每只票净偏哪边)——比按表态总数干净,不被高频标的主导
    stanced=[s for s in syms if we[s][0]+we[s][1]>0]
    nbull=sum(1 for s in stanced if we[s][0]>we[s][1])
    nbear=sum(1 for s in stanced if we[s][1]>we[s][0])
    ntie=sum(1 for s in stanced if we[s][0]==we[s][1])
    npure=sum(1 for s in stanced if we[s][0]==0 and we[s][1]>0)
    nst=len(stanced) or 1
    pbk=round(nbull/nst*100); prk=round(nbear/nst*100); pnk=100-pbk-prk
    # 可排序总表:近90日 >=3 次提及,默认按提及次数降序
    rows=sorted([s for s in syms if cnt(s,Q0,DAY)>=3], key=lambda s:-cnt(s,Q0,DAY))
    def qrow(s):
        c=cnt(s,Q0,DAY); eb,er,en=we[s]; pct=mention_pct(s)
        dchg='' if pct is None else f'{pct:.4f}'
        ind=ind_label(s) or '<span class="muted">—</span>'
        return (f'<tr onclick="dd(\'{s}\')" data-chg="{dchg}" data-men="{c}" data-bull="{eb}" data-bear="{er}" data-neu="{en}">'
            f'<td class="q-tk">{s}{market_pill(s)}{theme_pill(s)}{report_update_pill(s)}</td><td class="q-ind">{ind}</td>'
            f'<td class="q-dt">{ymd(first(s))}{pxcell(first_px(s),s)}</td><td class="q-dt">{ymd(last(s))}{pxcell(last_px(s),s)}</td>'
            f'<td class="q-chg">{mention_chg(s)}</td><td class="q-n men"><b>{c}</b></td>'
            f'<td class="q-n b">{eb}</td><td class="q-n r">{er}</td><td class="q-n n">{en}</td></tr>')
    thead=(f'<thead><tr><th>{t("th_ticker")}</th><th>{t("th_industry")}</th><th>{t("th_first")}</th><th>{t("th_last")}</th>'
        f'<th class="sortable num" data-dir="" onclick="qsort(\'chg\',this)">{t("th_gain")} <span class="qinfo" data-tip="{t("gain_formula_tip")}" onclick="event.stopPropagation()"><i class="fa-regular fa-circle-question"></i></span><span class="sar"></span></th>'
        f'<th class="sortable num on" data-dir="desc" onclick="qsort(\'men\',this)">{t("th_mentions")}<span class="sar"></span></th>'
        f'<th class="sortable num" data-dir="" onclick="qsort(\'bull\',this)">{t("th_bull")}<span class="sar"></span></th>'
        f'<th class="sortable num" data-dir="" onclick="qsort(\'bear\',this)">{t("th_bear")}<span class="sar"></span></th>'
        f'<th class="sortable num" data-dir="" onclick="qsort(\'neu\',this)">{t("th_neu")}<span class="sar"></span></th></tr></thead>')
    table=f'<div class="stbl-wrap"><table class="stbl" id="qtbl">{thead}<tbody>{"".join(qrow(s) for s in rows)}</tbody></table></div>'
    return f'''<section id="quarter" class="period-sec">
<div class="sec"><div class="sechd"><div class="st">{t('nav_quarter')}</div><div class="datepill">{Q0.strftime("%Y-%m-%d")} ~ {DAY.strftime("%m-%d")}</div>
<div class="sn"><span class="cnt">{t('quarter_count',n=len(syms),v=all_v)}</span><span class="upd">{t('updated',date=UPDATE_STAMP)}</span></div></div>
<div class="subhd">{t('subhd_q_overview')}</div></div>
<div class="daypad">
<div class="ovbox">
<div class="ovstats"><div class="ovs"><div class="ovn gb">{nbull}</div><div class="ovl">{t('q_net_bull')}</div></div>
<div class="ovs"><div class="ovn gr">{nbear}</div><div class="ovl">{t('q_net_bear')}</div></div>
<div class="ovs"><div class="ovn">{ntie}</div><div class="ovl">{t('q_balanced')}</div></div>
<div class="ovs"><div class="ovn">{len(stanced)}</div><div class="ovl">{t('q_with_stance')}</div></div></div>
<div class="ovbar"><i class="b" style="width:{pbk}%"></i><i class="r" style="width:{prk}%"></i><i class="n" style="width:{pnk}%"></i></div>
<div class="ovcap">{t('q_summary',pbk=pbk,prk=prk,npure=npure,TB=TB,TR=TR,TN=TN)}</div>
</div>
<div class="subhd" style="margin-top:28px">{t('subhd_q_table')} <span style="color:var(--ink-soft);font-weight:400;font-size:12.5px">　{t('q_table_hint',n=len(rows))}</span></div>
{table}
</div><div style="height:40px"></div></section>'''

def _h(x):
    return html.escape(str(x if x is not None else ''), quote=True)

def _report_citation_count(report):
    ids=set()
    for src in report.get('source_posts_used') or []:
        if src.get('tweet_id'): ids.add(str(src.get('tweet_id')))
    for sec in report.get('sections') or []:
        for c in sec.get('citations') or []:
            if c.get('tweet_id'): ids.add(str(c.get('tweet_id')))
    for upd in report.get('updates') or []:
        for tid in upd.get('source_tweet_ids') or []:
            if tid: ids.add(str(tid))
    return len(ids)

def _report_health(report):
    sections=len(report.get('sections') or [])
    cites=_report_citation_count(report)
    coverage=report.get('coverage_through') or ''
    if sections>=8 and cites>=8 and coverage:
        return ('ok','合格')
    if sections>=5 and cites>=5:
        return ('warn','需複查')
    return ('bad','不足')

def _serenity_signal_score(s):
    mentions=total(s)
    if mentions<=0:
        return None
    eb,er,en=win_exp(s,datetime.date(1970,1,1),DAY)
    stance_posts=eb+er+en
    if eb<=er or eb==0:
        return None
    w7=cnt(s,DAY-datetime.timedelta(days=6),DAY)
    w28=cnt(s,DAY-datetime.timedelta(days=27),DAY)
    last_seen=last(s)
    days_since=(DAY-last_seen).days if last_seen else 999
    net=eb-er
    net_ratio=net/max(1,stance_posts)
    stance_score=min(34, net*1.8 + eb*.35 + net_ratio*18)
    attention_score=min(24, mentions*.35 + w28*1.05 + w7*2.6)
    recency_score=max(0, 12 - min(days_since,36)/3)
    reason_text=' '.join(r for _,_,r,_ in exp[s] if r).lower()
    thesis_terms=('favorite','high conviction','best','compelling','room to go','love','long','buying','roi','winner','thesis')
    thesis_score=min(7, sum(1 for term in thesis_terms if term in reason_text)*1.4)
    risk_penalty=min(18, er*1.1 + (6 if en and en>=eb*.35 else 0))
    raw=stance_score+attention_score+recency_score+thesis_score-risk_penalty
    score=max(0,min(100,round(raw)))
    reasons=[]
    if eb:
        reasons.append(f'{eb} 則看多')
    if w28:
        reasons.append(f'近 28 日 {w28} 次提及')
    if er:
        reasons.append(f'{er} 則看空訊號需留意')
    return {
        'ticker':s,'score':score,'bull':eb,'bear':er,'neutral':en,
        'mentions':mentions,'w28':w28,'w7':w7,'last':ymd(last_seen),
        'reasons':reasons[:4]
    }

def serenity_top_signals(n=3, require_report=False):
    items=[]
    for s in mdates:
        if require_report and s not in REPORTS:
            continue
        item=_serenity_signal_score(s)
        if item:
            items.append(item)
    items.sort(key=lambda x:(x['score'], x['w28'], x['mentions'], x['bull']), reverse=True)
    return items[:n]

def _decision_reason(item):
    bits=[]
    mentions=item.get('total_mentions')
    days=item.get('unique_mention_days')
    if mentions and days:
        bits.append(f'累計 {mentions} 次提及，橫跨 {days} 天')
    elif mentions:
        bits.append(f'累計 {mentions} 次提及')
    why=item.get('why') or []
    for w in why:
        m=re.search(r'(\d+)\s+explicit stance posts', str(w))
        if m:
            bits.append(f'{m.group(1)} 則明確表態')
            continue
        m=re.search(r'(\d+)\s+substantive thesis-like posts', str(w))
        if m:
            bits.append(f'{m.group(1)} 則具論點內容')
            continue
        m=re.search(r'(\d+)\s+risk/caution posts', str(w))
        if m:
            bits.append(f'{m.group(1)} 則風險 / 謹慎訊號')
            continue
        m=re.search(r'(\d+)\s+high-conviction mentions', str(w))
        if m:
            bits.append(f'{m.group(1)} 則高信心提及')
            continue
        if str(w).startswith('high-signal terms:'):
            terms=str(w).split(':',1)[1].strip()
            if terms:
                bits.append('高訊號詞：'+terms)
    return ' · '.join(bits[:3]) or f'{PROFILE_NAME} 訊號足夠，值得整理成完整投資論點'

def _decision_action_class(action):
    return {
        'write_new_thesis':'new',
        'write_update':'upd',
        'regenerate_thesis':'regen',
        'watch_for_more_signal':'watch',
        'no_action':'ok',
    }.get(action,'watch')

def reports_section():
    summary=REPORT_QUEUE.get('summary') or {}
    dsummary=REPORT_DECISIONS.get('summary') or {}
    automation_next=REPORT_DECISIONS.get('automation_next') or []
    if not automation_next:
        automation_next=REPORT_QUEUE.get('next_reports') or []
    updates_due=REPORT_QUEUE.get('updates_due') or []
    published=[]
    updated=[]
    for s,report in sorted(REPORTS.items(), key=lambda kv:(kv[1].get('generated_at') or '', kv[0]), reverse=True):
        coverage=report.get('coverage_through') or '—'
        gen=(report.get('generated_at') or '')[:10] or '—'
        title=report.get('title') or co_of(s)
        updates=report.get('updates') or []
        newest_update=updates[0] if updates else None
        published.append(
            f'<article class="memo-card" onclick="dd(\'{s}\')">'
            f'<div class="memo-top"><div class="memo-ticker">{s}{market_pill(s)}{theme_pill(s)}</div>{report_update_pill(s)}</div>'
            f'<h3>{_h(title)}</h3><p>{_h(report.get("subtitle") or report.get("core_label") or co_of(s))}</p>'
            f'<div class="memo-meta"><span>覆蓋至 <b>{_h(coverage)}</b></span><span>生成日 <b>{_h(gen)}</b></span></div>'
            f'</article>'
        )
        if newest_update:
            updated.append((newest_update.get('date') or '', s, newest_update, report))
    updated.sort(key=lambda x:(x[0], x[1]), reverse=True)
    updated_cards=[]
    for date,s,u,report in updated[:6]:
        updated_cards.append(
            f'<article class="memo-update" onclick="dd(\'{s}\')">'
            f'<div class="memo-update-k"><i class="fa-solid fa-file-lines"></i>{_h(date or "—")}</div>'
            f'<div class="memo-update-t">{s}{market_pill(s)}{theme_pill(s)}</div>'
            f'<h3>{_h(u.get("title") or report.get("title") or co_of(s))}</h3>'
            f'<p>{_h(u.get("summary") or report.get("subtitle") or "")}</p>'
            f'</article>'
        )
    candidate_cards=[]
    for item in automation_next[:10]:
        s=(item.get('ticker') or '').upper()
        reason=_decision_reason(item)
        candidate_cards.append(
            f'<article class="memo-candidate" onclick="dd(\'{s}\')">'
            f'<div class="memo-ticker">{_h(s)}{market_pill(s)}{theme_pill(s)}</div>'
            f'<h3>{_h(item.get("company") or co_of(s))}</h3>'
            f'<p>{_h(reason)}</p>'
            f'<div class="memo-meta"><span>最近提及 <b>{_h(item.get("last_mention") or "—")}</b></span><span>提及 <b>{_h(item.get("total_mentions") or "—")}</b></span></div>'
            f'</article>'
        )
    candidate_empty='<div class="ops-empty">目前沒有新的候選投資論點。</div>' if not candidate_cards else ''
    top_cards=[]
    for i,item in enumerate(serenity_top_signals(),1):
        s=item['ticker']
        why=' · '.join(item['reasons']) or f'{PROFILE_NAME} 綜合訊號較強'
        medal_cls={1:'gold',2:'silver',3:'bronze'}.get(i,'')
        medal_icon='fa-crown' if i==1 else 'fa-medal'
        memo_state='' if s in REPORTS else '<span class="signal-missing"><i class="fa-regular fa-file-lines"></i> 尚未整理</span>'
        top_cards.append(
            f'<article class="signal-card rank-{medal_cls}" onclick="dd(\'{s}\')">'
            f'<div class="signal-rank {medal_cls}"><i class="fa-solid {medal_icon}"></i><span>#{i}</span></div><div class="signal-main">'
            f'<div class="signal-t">{_h(s)}{market_pill(s)}{theme_pill(s)}{memo_state}</div>'
            f'<h3>{_h(co_of(s))}</h3><p>{_h(why)}</p>'
            f'<div class="signal-meta"><span>看多 <b>{item["bull"]}</b></span><span>看空 <b>{item["bear"]}</b></span><span>最近 <b>{_h(item["last"])}</b></span></div>'
            f'</div><div class="signal-score"><b>{item["score"]}</b><span>score</span></div></article>'
        )
    top_empty='<div class="ops-empty">目前沒有足夠的看多訊號可排序。</div>' if not top_cards else ''
    automation_ready=dsummary.get('automation_ready', summary.get('needs_report',0))
    return f'''<section id="reports" class="period-sec">
<div class="sec"><div class="sechd"><div class="st">{t('nav_reports')}</div><div class="datepill">investment memo</div>
<div class="sn"><span class="cnt">已發布 {len(REPORTS)} 份 · 下一批 {automation_ready} 檔 · 待更新 {len(updates_due)} 份</span><span class="upd">{t('updated',date=UPDATE_STAMP)}</span></div></div></div>
<div class="daypad">
<div class="subhd" style="margin-top:0"><i class="fa-solid fa-ranking-star"></i> {PROFILE_NAME} <span class="jargon" role="button" tabindex="0">綜合訊號<span class="jargon-tip">依 {PROFILE_NAME} 的公開貼文計算：看多強度、近期熱度、語氣強度，以及看空 / 分歧訊號扣分。尚未整理的高分標的會優先進入投資論點生成。</span></span> Top 3</div>
<div class="signal-grid">{''.join(top_cards)}{top_empty}</div>
<div class="subhd" style="margin-top:24px"><i class="fa-solid fa-bolt"></i> 最近更新</div>
<div class="memo-updates">{''.join(updated_cards) if updated_cards else '<div class="ops-empty">目前沒有新的投資論點更新。</div>'}</div>
<div class="subhd" style="margin-top:24px"><i class="fa-solid fa-book-open"></i> 已發布投資論點</div>
<div class="memo-grid">{''.join(published)}</div>
<div class="subhd" style="margin-top:26px"><i class="fa-solid fa-list-check"></i> 待整理候選</div>
<div class="memo-candidates">{''.join(candidate_cards)}{candidate_empty}</div>
</div><div style="height:40px"></div></section>'''

W7=(DAY-datetime.timedelta(days=6),DAY)
DAYCFG=dict(id='day',title=t('nav_day'),pfx=t('pfx_day'),win=(DAY,DAY),big=3,head=t('head_day_mentions'),
  freq=[(t('freq_7d'),'w7'),(t('freq_28d'),'w28')],chg='daily',chglbl=t('chg_daily_lbl'),
  pill=str(DAY),range=t('pfx_day'),subhd=t('subhd_day'))
WKCFG=dict(id='week',title=t('nav_week'),pfx=t('pfx_week'),win=W7,big=10,head=t('head_week_mentions'),
  freq=[(t('freq_near28'),'w28')],chg='mention',chglbl=t('gain_lbl'),
  pill=f'{W7[0].strftime("%Y-%m-%d")} ~ {DAY.strftime("%m-%d")}',range=t('freq_near7'),subhd=t('subhd_week'))

SHARED_CSS='''<style>
.card.big{display:flex;flex-direction:column}
.cfoot{margin-top:auto;padding-top:14px}
.pchg-r{margin-left:auto;align-self:center;display:flex;align-items:center;gap:6px;font-family:var(--mono);font-size:11px;color:var(--ink-faint)}
.pchg-lbl{font-size:10.5px}
.chg{font-family:var(--mono);font-size:11px;padding:1px 7px;border-radius:4px;font-weight:600}
.chg.pending{background:var(--paper);color:var(--ink-faint);border:1px dashed var(--line-strong);font-weight:400}
.chg.up{background:var(--bull-bg);color:var(--bull)}.chg.down{background:var(--bear-bg);color:var(--bear)}
.market{display:inline-flex;align-items:center;vertical-align:middle;margin-left:6px;padding:1px 6px;border:1px solid var(--line);border-radius:999px;background:var(--paper);color:var(--ink-soft);font-family:var(--mono);font-size:9.5px;font-weight:700;line-height:1.35}
.market.detail{font-size:11px;margin-left:10px;transform:translateY(-4px)}
.theme{display:inline-flex;align-items:center;vertical-align:middle;margin-left:5px;padding:1px 7px;border:1px solid rgba(29,155,240,.22);border-radius:999px;background:rgba(29,155,240,.07);color:#1d6fa5;font-family:var(--mono);font-size:9.5px;font-weight:700;line-height:1.35;white-space:nowrap}
.theme.other{border-color:var(--line);background:var(--paper);color:var(--ink-faint)}
.theme.detail{font-size:11px;margin-left:6px;transform:translateY(-4px)}
.updchip{position:relative;display:inline-flex;align-items:center;gap:4px;vertical-align:middle;margin-left:6px;padding:2px 7px;border:1px solid rgba(31,92,77,.24);border-radius:999px;background:var(--accent-soft);color:var(--accent);font-family:var(--mono);font-size:9.5px;font-weight:700;line-height:1.35;white-space:nowrap}
.updchip i{font-size:9px}
.updchip.fresh{animation:updatePulse 2.6s ease-in-out infinite}
.updchip.fresh::after{content:"";position:absolute;inset:-4px;border:1px solid rgba(31,92,77,.22);border-radius:999px;opacity:0;animation:updateRing 2.6s ease-out infinite;pointer-events:none}
@keyframes updatePulse{0%,100%{box-shadow:0 0 0 rgba(31,92,77,0)}45%{box-shadow:0 0 0 3px rgba(31,92,77,.08)}}
@keyframes updateRing{0%{transform:scale(.96);opacity:.7}72%,100%{transform:scale(1.22);opacity:0}}
@media (prefers-reduced-motion:reduce){.updchip.fresh,.updchip.fresh::after{animation:none}}
.rchip em{font-style:normal;color:var(--ink-soft);font-size:9.5px}
.surfrow .rrt{margin-left:auto;display:flex;align-items:center;gap:10px}
.badge.cw{background:#f3e7cc;color:#8a6a1f}.card.cw::before{background:var(--gold)}
.distrow .dlbl{font-size:11px;color:var(--ink-faint)}
.qtag{display:inline-block;background:var(--ink);color:#fff;font-size:10px;padding:1px 6px;border-radius:3px;margin-right:6px;font-family:var(--mono);letter-spacing:.5px;vertical-align:middle}
.csumm{font-size:12.5px;line-height:1.6;color:var(--ink-soft);font-style:italic}
.qlink{color:var(--ink);text-decoration:none;border-bottom:1px dotted var(--accent);font-style:italic}.qlink:hover{color:var(--accent)}
.daypad{padding:0 44px}
.surfrow{display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;padding:9px 14px;background:var(--card);border:1px solid var(--line);border-left:3px solid var(--neutral);border-radius:6px;margin-bottom:7px;cursor:pointer;font-size:13px}
.surfrow .tk{font-family:var(--mono);font-weight:700;font-size:14px;min-width:62px}.surfrow .sco2{color:var(--ink-soft);min-width:150px;font-size:12px}
.surfrow .sfreq{font-family:var(--mono);font-size:11px;color:var(--ink-faint);white-space:nowrap}.surfrow .go{color:var(--accent);font-size:11px;white-space:nowrap}
.stag{font-size:11px;padding:2px 8px;border-radius:10px;font-weight:600;white-space:nowrap}.stag.bear{background:var(--bear-bg);color:var(--bear)}.stag.cw{background:#f3e7cc;color:#8a6a1f}
.cbox{background:var(--card);border:1px dashed var(--line-strong);border-radius:8px;padding:14px 16px;font-size:12.5px;color:var(--ink-soft);line-height:1.95;margin-bottom:14px}
.rchip{display:inline-block;font-family:var(--mono);font-size:11px;background:var(--paper);border:1px solid var(--line);border-radius:4px;padding:1px 7px;margin:2px;cursor:pointer;color:var(--ink)}
.morechip{display:inline-block;font-size:11px;border:1px dashed var(--line-strong);border-radius:4px;padding:1px 9px;margin:2px;cursor:pointer;color:var(--ink-soft);background:transparent}
.morechip:hover{color:var(--accent);border-color:var(--accent)}
.ops-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:8px 0 22px}
.ops-card{border:1px solid var(--line);background:var(--card);border-radius:8px;padding:14px 15px}
.ops-card span{display:block;font-size:11.5px;color:var(--ink-soft);margin-bottom:7px}
.ops-card b{font-family:var(--mono);font-size:24px;color:var(--ink)}
.ops-table-wrap{overflow:auto;border:1px solid var(--line);border-radius:8px;background:var(--card)}
.ops-table{width:100%;border-collapse:collapse;table-layout:fixed;font-size:12.5px;min-width:780px}
.ops-col-ticker{width:190px}.ops-col-date{width:126px}.ops-col-score{width:92px}.ops-col-count{width:82px}.ops-col-action{width:150px}
.ops-published .ops-col-ticker{width:220px}
.ops-table th{position:sticky;top:0;background:var(--paper);color:var(--ink-faint);font-family:var(--mono);font-size:10.5px;text-align:left;font-weight:700;padding:9px 10px;border-bottom:1px solid var(--line)}
.ops-table td{padding:10px;border-bottom:1px solid var(--line);vertical-align:middle;color:var(--ink-soft)}
.ops-table tr{cursor:pointer}.ops-table tr:hover td{background:var(--paper)}
.ops-table tr:last-child td{border-bottom:none}
.ops-tk{font-family:var(--mono);font-weight:800;color:var(--ink);white-space:normal;line-height:1.55}
.ops-title{color:var(--ink);line-height:1.45;overflow:hidden;text-overflow:ellipsis}
.ops-title b{display:block;color:var(--ink);font-weight:650;margin-bottom:2px}
.ops-title span{display:block;color:var(--ink-soft);font-size:12px;line-height:1.55;white-space:normal}
.ops-num{font-family:var(--mono);text-align:left;color:var(--ink)}
.ops-action{display:inline-flex;align-items:center;border-radius:999px;padding:3px 8px;font-size:11px;font-weight:700;border:1px solid var(--line);white-space:nowrap}
.ops-action.new{background:rgba(29,155,240,.08);color:#1d6fa5;border-color:rgba(29,155,240,.22)}
.ops-action.upd{background:var(--bull-bg);color:var(--bull);border-color:rgba(31,122,77,.18)}
.ops-action.regen{background:#f3e7cc;color:#8a6a1f;border-color:rgba(138,106,31,.2)}
.ops-action.watch{background:var(--paper);color:var(--ink-soft)}
.ops-action.ok{background:var(--paper);color:var(--ink-faint)}
.ops-status{display:inline-flex;border-radius:999px;padding:3px 8px;font-family:var(--mono);font-size:10.5px;font-weight:700;border:1px solid var(--line);white-space:nowrap}
.ops-status.ok{background:var(--bull-bg);color:var(--bull);border-color:rgba(31,122,77,.18)}
.ops-status.warn{background:#f3e7cc;color:#8a6a1f;border-color:rgba(138,106,31,.2)}
.ops-status.bad{background:var(--bear-bg);color:var(--bear);border-color:rgba(173,65,65,.2)}
.ops-empty{border:1px dashed var(--line-strong);border-radius:8px;padding:14px;color:var(--ink-soft);font-size:12.5px;background:var(--card)}
.ops-empty-cell{padding:18px!important;color:var(--ink-soft);text-align:center;font-size:12.5px}
.ops-fails{display:grid;gap:8px}
.ops-fail{border:1px solid rgba(173,65,65,.22);border-radius:8px;background:var(--bear-bg);padding:12px 14px}
.ops-fail b{font-family:var(--mono);color:var(--bear);margin-right:8px}.ops-fail span{font-family:var(--mono);font-size:10.5px;color:var(--ink-faint)}.ops-fail p{font-size:12.5px;color:var(--ink-soft);margin-top:6px;line-height:1.55}
@media(max-width:820px){.ops-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.ops-card b{font-size:21px}.ops-col-action{width:128px}.ops-candidates{min-width:720px}}
.memo-updates{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.memo-update{position:relative;border:1px solid rgba(31,92,77,.22);border-left:4px solid var(--accent);border-radius:8px;background:linear-gradient(90deg,rgba(31,92,77,.08),var(--card) 58%);padding:14px 16px;cursor:pointer;box-shadow:0 10px 24px -24px rgba(31,92,77,.65);transition:border-color .16s ease,box-shadow .16s ease,transform .16s ease,background .16s ease}
.memo-update:hover{transform:translateY(-2px);border-color:rgba(31,92,77,.46);border-left-color:#17483c;background:linear-gradient(90deg,rgba(31,92,77,.16),rgba(31,92,77,.055) 46%,var(--card) 100%);box-shadow:0 18px 34px -24px rgba(31,92,77,.95)}
.memo-card:hover,.memo-candidate:hover{border-color:rgba(31,92,77,.32);box-shadow:0 10px 24px -22px rgba(31,92,77,.65)}
.memo-update-k{font-family:var(--mono);font-size:10.5px;font-weight:800;color:var(--accent);letter-spacing:.02em;display:flex;align-items:center;gap:6px;margin-bottom:8px}
.memo-update-t,.memo-ticker{font-family:var(--mono);font-weight:800;color:var(--ink);display:flex;align-items:center;gap:4px;flex-wrap:wrap;line-height:1.45}
.memo-update h3,.memo-card h3,.memo-candidate h3{font-family:var(--serif);font-size:16px;font-weight:900;line-height:1.32;color:var(--ink);margin:7px 0 6px}
.memo-update p,.memo-card p,.memo-candidate p{font-size:12.5px;line-height:1.65;color:var(--ink-soft);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.memo-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.memo-card,.memo-candidate{border:1px solid var(--line);border-radius:8px;background:var(--card);padding:14px 16px;cursor:pointer;min-width:0}
.memo-top{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;flex-wrap:wrap}
.memo-meta{display:flex;gap:12px;flex-wrap:wrap;margin-top:10px;font-family:var(--mono);font-size:10.5px;color:var(--ink-faint)}
.memo-meta b{color:var(--ink);font-weight:800}
.memo-candidates{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.memo-candidate{padding:12px 14px}
.memo-candidate h3{font-family:var(--sans);font-size:14px;margin-top:5px}
.signal-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
.signal-card{position:relative;display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:12px;align-items:start;border:1px solid rgba(31,92,77,.2);border-radius:8px;background:linear-gradient(180deg,rgba(31,92,77,.045),var(--card) 58%);padding:15px 16px;cursor:pointer;min-width:0;transition:border-color .16s ease,box-shadow .16s ease,transform .16s ease,background .16s ease}
.signal-card.rank-gold{border-color:rgba(186,134,22,.58);background:linear-gradient(180deg,rgba(236,180,43,.24),rgba(236,180,43,.055) 58%,var(--card) 100%)}
.signal-card.rank-silver{border-color:rgba(136,145,151,.56);background:linear-gradient(180deg,rgba(184,192,198,.22),rgba(184,192,198,.05) 58%,var(--card) 100%)}
.signal-card.rank-bronze{border-color:rgba(178,93,45,.54);background:linear-gradient(180deg,rgba(198,106,50,.22),rgba(198,106,50,.05) 58%,var(--card) 100%)}
.signal-card:hover{transform:translateY(-2px);box-shadow:0 18px 34px -26px rgba(31,92,77,.75)}
.signal-card.rank-gold:hover{border-color:rgba(186,134,22,.82);background:linear-gradient(180deg,rgba(236,180,43,.34),rgba(236,180,43,.085) 55%,var(--card) 100%);box-shadow:0 18px 34px -24px rgba(186,134,22,1)}
.signal-card.rank-silver:hover{border-color:rgba(136,145,151,.82);background:linear-gradient(180deg,rgba(184,192,198,.32),rgba(184,192,198,.08) 55%,var(--card) 100%);box-shadow:0 18px 34px -24px rgba(136,145,151,.95)}
.signal-card.rank-bronze:hover{border-color:rgba(178,93,45,.8);background:linear-gradient(180deg,rgba(198,106,50,.32),rgba(198,106,50,.08) 55%,var(--card) 100%);box-shadow:0 18px 34px -24px rgba(178,93,45,.95)}
.signal-rank{font-family:var(--mono);font-size:12px;font-weight:900;color:var(--accent);border:1px solid rgba(31,92,77,.25);background:var(--accent-soft);border-radius:999px;padding:4px 8px;line-height:1;display:inline-flex;align-items:center;gap:5px;white-space:nowrap}
.signal-rank i{font-size:11px}.signal-rank.gold{color:#7b5200;border-color:rgba(186,134,22,.74);background:rgba(236,180,43,.34)}
.signal-rank.silver{color:#4f585e;border-color:rgba(136,145,151,.72);background:rgba(184,192,198,.32)}
.signal-rank.bronze{color:#743817;border-color:rgba(178,93,45,.72);background:rgba(198,106,50,.3)}
.signal-main{min-width:0}.signal-t{font-family:var(--mono);font-weight:850;color:var(--ink);display:flex;align-items:center;gap:4px;flex-wrap:wrap;line-height:1.45}
.signal-missing{display:inline-flex;align-items:center;gap:4px;border:1px dashed rgba(31,92,77,.32);border-radius:999px;background:rgba(31,92,77,.045);color:var(--accent);font-size:9px;font-weight:850;padding:1px 6px;line-height:1.45}
.signal-card h3{font-family:var(--serif);font-size:16px;font-weight:900;line-height:1.28;color:var(--ink);margin:8px 0 6px}
.signal-card p{font-size:12.5px;line-height:1.6;color:var(--ink-soft);margin:0;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.signal-meta{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px;font-family:var(--mono);font-size:10.5px;color:var(--ink-faint)}
.signal-meta b{color:var(--ink);font-weight:850}.signal-score{text-align:right;font-family:var(--mono);color:var(--ink-faint);min-width:44px}
.signal-score b{display:block;font-size:25px;line-height:1;color:var(--accent)}.signal-score span{display:block;font-size:9.5px;font-weight:800;text-transform:uppercase;letter-spacing:.03em;margin-top:3px}
.rank-gold .signal-score b{color:#9a6900}.rank-silver .signal-score b{color:#5f6870}.rank-bronze .signal-score b{color:#88441d}
@media(max-width:1050px){.signal-grid{grid-template-columns:1fr}}
@media(max-width:900px){.memo-updates,.memo-grid,.memo-candidates{grid-template-columns:1fr}}
@media(max-width:600px){.memo-update h3,.memo-card h3{font-size:15.5px}}
.twocol{display:grid;grid-template-columns:1fr 1fr;gap:30px;margin-top:6px}
.mwall{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-bottom:6px}
.mcard{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--neutral);border-radius:8px;padding:13px 15px;cursor:pointer;box-shadow:var(--shadow);display:flex;flex-direction:column;min-width:0;overflow-wrap:break-word}
.mcard.bull{border-left-color:var(--bull)}.mcard.bear{border-left-color:var(--bear)}.mcard.cw{border-left-color:var(--gold)}
.mcard .mh{display:flex;align-items:center;gap:8px;margin-bottom:3px}
.mcard .mh .tk{font-family:var(--mono);font-weight:700;font-size:15px}
.mcard .mco{font-size:12px;color:var(--ink);margin-bottom:7px}.mcard .mco .ind{color:var(--ink-faint);font-size:10.5px}
.mcard .mline{font-family:var(--mono);font-size:11px;color:var(--ink-faint);padding:6px 0;border-top:1px dashed var(--line);display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.mcard .mreason{font-size:11.5px;color:var(--ink-soft);font-style:italic;padding-top:6px;border-top:1px dashed var(--line)}
.trow .badge.mini{margin-left:0}
.subhd{font-size:13.5px;color:var(--ink-soft);margin:20px 0 14px}
.trow{display:grid;grid-template-columns:26px 70px minmax(160px,220px) minmax(150px,175px) minmax(80px,1fr) 102px 140px 74px;align-items:center;gap:12px;padding:11px 4px;border-bottom:1px dashed var(--line);cursor:pointer}
.trow:hover{background:var(--card)}
.trow .trk,.trow .ttk,.trow .tn{width:auto}.trow .trk{text-align:center}
.trow .ttk{display:flex;align-items:center;gap:4px;flex-wrap:wrap;min-width:0;line-height:1.35}
.trow .distbar{height:15px;min-width:0;border-radius:5px}
.ttag{display:flex;align-items:center}
.tchg{font-family:var(--mono);font-size:10px;color:var(--ink-faint);display:flex;align-items:center;gap:5px;white-space:nowrap;justify-content:flex-end}
.colhd{font-family:var(--serif);font-weight:700;font-size:16px;margin-bottom:12px;color:var(--ink);display:flex;align-items:center;gap:7px}
.toplist{max-width:none;padding:0}
.tn2{font-family:var(--mono);font-size:12px;color:var(--ink);white-space:nowrap}.tn2 b{font-weight:700}
@media(max-width:860px){
  .trow{display:flex;flex-wrap:wrap;align-items:center;gap:3px 8px;padding:11px 2px}
  .trow .trk{width:20px}
  .trow .ttk{width:auto;font-size:14px}
  .trow .ttag{order:2}
  .trow .tchg{order:3;margin-left:auto;justify-content:flex-end}
  .trow .distnum{order:4;flex:0 0 100%;white-space:normal}
  .trow .distbar{order:5;flex:0 0 100%;width:100%;max-width:none;height:12px;justify-self:stretch}
  .trow .bgonly{flex:0 0 100%}
  .trow .tn2{order:6}
  .trow .sgo{order:7;margin-left:auto}
  .surfrow{flex-wrap:wrap;gap:5px 8px;padding:10px 12px}
  .surfrow .tk{min-width:0}
  .surfrow .sco2{min-width:0;flex:1 1 auto}
  .surfrow .rrt{flex:0 0 100%;margin-left:0;justify-content:space-between;flex-wrap:wrap;gap:6px}
}
.ovbox{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:22px 26px}
.ovstats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:18px;margin-bottom:18px}
.ovs{text-align:center}.ovs .ovn{font-family:var(--serif);font-weight:900;font-size:34px;line-height:1}.ovs .ovl{font-size:12px;color:var(--ink-soft);margin-top:6px}
.ovbar{height:22px;border-radius:6px;overflow:hidden;display:flex;background:var(--paper)}
.ovbar i{display:block;height:100%}.ovbar .b{background:var(--bull)}.ovbar .r{background:var(--bear)}.ovbar .n{background:#cfc7b2}
.ovcap{font-size:12.5px;color:var(--ink-soft);margin-top:10px}.ovcap .gb{color:var(--bull)}.ovcap .gr{color:var(--bear)}
.stackwrap{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:20px 26px}
.thlegend{display:flex;gap:18px;margin-bottom:16px;flex-wrap:wrap}
.thleg{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--ink-soft)}.thleg i{width:12px;height:12px;border-radius:3px;display:inline-block}
.stackchart{display:flex;gap:40px;align-items:flex-end;justify-content:center;padding:0 20px;min-height:185px}
.scol{display:flex;flex-direction:column;align-items:center;gap:8px;flex:1;max-width:200px}
.scolbars{display:flex;flex-direction:column;justify-content:flex-end;width:72px;height:150px}
.sseg{width:100%}.sseg:first-child{border-radius:4px 4px 0 0}
.scollbl{font-family:var(--mono);font-size:11px;color:var(--ink-faint);text-align:center;line-height:1.5}.scollbl b{color:var(--ink);font-size:13px}
.rank3{display:grid;grid-template-columns:repeat(3,1fr);gap:20px}
.rkcol{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 18px}
.rkhd{font-family:var(--serif);font-weight:700;font-size:15px;margin-bottom:12px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.rkhint{font-family:var(--mono);font-size:10px;font-weight:400;color:var(--ink-faint)}
.rkrow{display:grid;grid-template-columns:64px 1fr auto auto;align-items:center;gap:8px;padding:7px 0;border-top:1px dashed var(--line);cursor:pointer;font-size:13px}
.rkrow:hover{background:var(--paper)}
.rktk{font-family:var(--mono);font-weight:700}.rkco{color:var(--ink-soft);font-size:11.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rksub{font-family:var(--mono);font-size:10.5px;color:var(--ink-faint)}.rksub .gb{color:var(--bull)}.rksub .gr{color:var(--bear)}
.rkc{font-family:var(--mono);font-weight:700;font-size:13px}.rkc.gb{color:var(--bull)}.rkc.gr{color:var(--bear)}
.rkhd2{font-family:var(--serif);font-weight:700;font-size:15.5px;margin:6px 0 8px;display:flex;align-items:baseline;gap:10px}
.rkhd2 .rkhint{font-family:var(--mono);font-size:11px;font-weight:400;color:var(--ink-faint)}
.wt{border:1px solid var(--line);border-radius:8px;overflow:hidden;background:var(--card);font-size:13px;margin-bottom:6px}
.wt-h,.wt-r{display:grid;grid-template-columns:110px 1fr 130px 130px 150px 110px 150px;align-items:center;gap:14px;padding:10px 20px}
.wt-h{background:var(--paper);font-family:var(--mono);font-size:11px;color:var(--ink-soft);border-bottom:1px solid var(--line);font-weight:600}
.wt-r{border-top:1px dashed var(--line);cursor:pointer}.wt-r:first-of-type{border-top:none}.wt-r:hover{background:var(--paper)}
.wt .ralign{text-align:right;justify-self:end}
.wtk{font-family:var(--mono);font-weight:700}.wth{color:var(--ink-soft);font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.wd{font-family:var(--mono);font-size:11.5px;color:var(--ink-faint)}
.wn b{font-family:var(--mono);font-size:14px}
.wdist{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;justify-self:end;width:138px}
.wdist .db{font-family:var(--mono);font-size:12.5px;font-weight:700;text-align:center;padding:4px 0;border-radius:4px;background:var(--paper);border:1px solid var(--line)}
.wdist .db.b{color:var(--bull)}.wdist .db.r{color:var(--bear)}.wdist .db.n{color:var(--ink-soft)}
.wdist .dh{font-size:10.5px;font-weight:600;text-align:center;color:var(--ink-soft)}
.wt .muted{color:var(--line-strong)}
@media(max-width:980px){.wt-h{display:none}.wt-r{grid-template-columns:1fr 1fr;gap:4px 10px}}
.moretoggle{text-align:center;font-family:var(--mono);font-size:12px;color:var(--accent);background:var(--card);border:1px dashed var(--line-strong);border-radius:8px;padding:11px;margin-top:8px;cursor:pointer}
.moretoggle:hover{background:var(--accent-soft)}
.trow .sgo{margin-left:0;font-family:var(--mono);font-size:10.5px;color:var(--accent);border:1px solid var(--line);border-radius:999px;padding:3px 13px;white-space:nowrap;justify-self:start;line-height:1.4}
.trow:hover .sgo{border-color:var(--accent)}
.trow .distnum{margin-left:0;min-width:auto}
.mtag{font-size:10px;padding:2px 7px;border-radius:9px;font-weight:600;white-space:nowrap}
.mtag.new{background:var(--accent-soft);color:var(--accent)}.mtag.act{background:#f3e7cc;color:#8a6a1f}
.leg{font-size:13px;color:var(--ink-soft);margin-top:14px;line-height:1.85}.leg .gb{color:var(--bull)}.leg .gr{color:var(--bear)}
.mcard .mline b{color:var(--ink)}.mcard .mline{flex-wrap:wrap;min-width:0}
.mwall>.mcard{min-width:0}.mcard .distbar{min-width:60px}
@media(max-width:1100px){.mwall{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:900px){.daypad{padding:0 20px}.twocol{grid-template-columns:1fr}.mwall{grid-template-columns:1fr}}
.ovnote{margin-top:10px;font-size:11.5px;color:var(--ink-faint)}.ovnote b{color:var(--ink-soft)}
.stbl-wrap{max-height:600px;overflow:auto;border:1px solid var(--line);border-radius:10px;background:var(--card);margin-top:6px}
table.stbl{width:100%;border-collapse:collapse;font-size:12.5px}
.stbl thead th{position:sticky;top:0;background:var(--paper);z-index:2;text-align:left;padding:11px 14px;font-size:11.5px;color:var(--ink-soft);font-weight:600;border-bottom:1px solid var(--line-strong);white-space:nowrap}
.stbl th.num{text-align:right}
.stbl th.sortable{cursor:pointer;user-select:none}
.stbl th.sortable:hover{color:var(--ink)}
.stbl th.sortable.on{color:var(--accent)}
.stbl .sar{font-size:9px;margin-left:3px;color:var(--ink-faint)}
.stbl th.sortable.on[data-dir=desc] .sar::after{content:'▼'}
.stbl th.sortable.on[data-dir=asc] .sar::after{content:'▲'}
.stbl tbody tr{border-top:1px dashed var(--line);cursor:pointer}
.stbl tbody tr:hover{background:var(--paper)}
.stbl td{padding:9px 14px;vertical-align:middle}
.stbl .q-tk{font-family:var(--mono);font-weight:700;white-space:nowrap}
.stbl .q-tk .market{margin-left:5px}
.stbl .q-tk .theme{margin-left:4px}
.stbl .q-ind{color:var(--ink-soft);max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.stbl .q-dt{font-family:var(--mono);font-size:11px;color:var(--ink-faint);white-space:nowrap}
.stbl .q-chg{text-align:right;white-space:nowrap}
.stbl .q-n{font-family:var(--mono);text-align:right;font-weight:700;white-space:nowrap}
.stbl .q-n.b{color:var(--bull)}.stbl .q-n.r{color:var(--bear)}.stbl .q-n.n{color:var(--ink-soft)}
.stbl .muted{color:var(--line-strong)}
@media(max-width:980px){.stbl .q-ind{max-width:120px}.stbl thead th,.stbl td{padding:8px 8px}}
.bgonly{color:var(--ink-faint);font-size:11px;font-style:italic}
/* ===== 响应式自适应(C 包,保持原设计) ===== */
@media(max-width:900px){
  .toplist,.qblock,.qoverview,.qbulls,.secsub,.cols2,.cols3,.empty{padding-left:20px;padding-right:20px}
  .qbigbar{margin-left:20px;margin-right:20px}
}
@media(max-width:600px){
  body{flex-direction:column}
  .sidenav{position:static;width:auto;flex-direction:row;align-items:center;gap:2px;border-right:none;border-bottom:1px solid var(--line);padding:8px 12px;overflow-x:auto}
  .sidenav .brand{padding:0 10px 0 0;margin:0 6px 0 0;border-bottom:none;border-right:1px dashed var(--line);display:flex;align-items:center;gap:8px;flex:0 0 auto}
  .sidenav .glyph{margin-bottom:0;width:30px;height:30px;font-size:15px}
  .sidenav .bt,.sidenav .bs,.navlink .ni{display:none}
  .navlink span:not(.ni){display:inline}
  .navlink{padding:7px 11px;border-left:none;border-bottom:2px solid transparent;font-size:14px;flex:0 0 auto}
  .navlink.on{border-left:none;border-bottom-color:var(--accent);background:transparent}
  .main{margin-left:0}
  .sec{padding:18px 14px 8px}
  .sechd{flex-wrap:wrap}
  .sechd .st{white-space:nowrap}
  .sechd .sn{margin-left:0;align-items:flex-start}
  .wall,.wall.smallwall,.daypad,.toplist,.qblock,.qoverview,.qbulls,.secsub,.cols2,.cols3,.shifts,.empty{padding-left:14px;padding-right:14px}
  .qbigbar{margin-left:14px;margin-right:14px}
  .wall,.wall.smallwall,.mwall,.twocol,.cols2,.cols3{grid-template-columns:1fr}
  #qtbl{min-width:660px}
  #ddBody{padding:18px 14px 80px}
  .ddmeta{text-align:left}
}
</style></head>'''

# ---- embedded base page <head> (CSS vars/fonts/layout base). render now writes the whole page itself. ----
BASE_HEAD='''<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>@aleabitoreddit 个股评论追踪</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>

:root{--paper:#f9f7f3;--card:#fbf9f4;--ink:#1c1a17;--ink-soft:#55514a;--ink-faint:#8a8479;--line:#dcd6c8;--line-strong:#c6bfae;--accent:#1f5c4d;--accent-soft:#e3ede8;--bull:#1f7a4d;--bull-bg:#e6f1e9;--bear:#a8392b;--bear-bg:#f4e3df;--neutral:#8a7a3f;--neutral-bg:#f0ebd9;--gold:#b8893a;--mono:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,monospace;--sans:'Inter',ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;--serif:'Inter',ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;--shadow:0 1px 0 rgba(0,0,0,.04),0 10px 28px -18px rgba(28,26,23,.38);}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--paper);font-family:var(--sans);font-feature-settings:"tnum","ss01","cv11","cv02";color:var(--ink);display:flex}
.sidenav{position:fixed;left:0;top:0;bottom:0;width:180px;background:var(--card);border-right:1px solid var(--line);padding:26px 0;display:flex;flex-direction:column;z-index:10}
.sidenav .brand{padding:0 22px 22px;border-bottom:1px dashed var(--line);margin-bottom:14px}
.sidenav .glyph{width:42px;height:42px;border:1px solid var(--line-strong);border-radius:50%;display:block;object-fit:cover;background:var(--card);margin-bottom:10px}
.sidenav .bt{font-family:var(--serif);font-weight:700;font-size:15px;line-height:1.2}
.sidenav .bs{font-family:var(--mono);font-size:9.5px;color:var(--ink-faint);margin-top:4px}
.navlink{display:flex;align-items:center;gap:10px;padding:11px 22px;font-family:var(--serif);font-size:15px;color:var(--ink-soft);text-decoration:none;border-left:3px solid transparent;cursor:pointer}
.navlink:hover{background:var(--paper)}
.navlink.on{color:var(--accent);border-left-color:var(--accent);font-weight:700;background:var(--accent-soft)}
.navlink .ni{display:none;font-family:var(--mono);font-size:10px;color:var(--ink-faint)}
.main{margin-left:180px;flex:1;min-width:0}
.sidenav .bs a{color:var(--accent);text-decoration:none;border-bottom:1px solid var(--accent)}
.crumb{font-family:var(--mono);font-size:11px;color:var(--ink-faint);display:flex;align-items:center;gap:7px;flex-wrap:wrap}
.crumb a{color:var(--ink-soft);text-decoration:none;border-bottom:1px solid transparent}
.crumb a:hover{color:var(--accent);border-bottom-color:rgba(31,92,77,.35)}
.crumb b{color:var(--ink);font-weight:800}.crumb .sep{color:var(--line-strong)}
.main>.crumb{padding:24px 44px 0}
.stbl .q-dt .qpx{display:block;font-family:var(--mono);font-size:10px;color:var(--ink-faint);margin-top:2px;font-weight:400}
.qinfo{display:inline-flex;align-items:center;justify-content:center;width:14px;height:14px;font-size:12px;font-weight:400;font-style:normal;color:var(--ink-faint);cursor:help;position:relative;vertical-align:middle}
.qinfo:hover{color:var(--accent)}
.qinfo:hover::after{content:attr(data-tip);position:absolute;top:160%;left:50%;transform:translateX(-50%);width:max-content;max-width:210px;white-space:normal;text-align:center;line-height:1.5;background:var(--ink);color:var(--paper);font-size:11px;font-weight:400;letter-spacing:normal;padding:7px 11px;border-radius:6px;z-index:60;box-shadow:0 4px 14px rgba(0,0,0,.2);pointer-events:none}
.sec{padding:34px 44px 10px}
.sechd{display:flex;align-items:baseline;gap:14px;border-bottom:2px solid var(--ink);padding-bottom:12px;margin-bottom:8px;cursor:pointer}
.sechd .st{font-family:var(--serif);font-weight:900;font-size:30px;display:inline-flex;align-items:center;gap:10px}
.sechd .datepill{font-family:var(--mono);font-weight:500;font-size:13px;color:var(--ink-soft);background:transparent;padding:0;border-radius:0;letter-spacing:0}
.sechd .sn{margin-left:auto;display:flex;flex-direction:column;align-items:flex-end;gap:4px}
.sechd .sn .cnt{font-family:var(--mono);font-size:12px;color:var(--accent);background:var(--accent-soft);padding:4px 12px;border-radius:5px}
.sechd .sn .upd{font-family:var(--mono);font-size:12px;color:var(--ink-soft);font-weight:500}
.sectoggle{border:1px solid var(--line);background:var(--card);color:var(--ink-soft);border-radius:999px;width:24px;height:24px;display:inline-flex;align-items:center;justify-content:center;cursor:pointer;font-size:10px;transition:border-color .16s ease,color .16s ease,background .16s ease,transform .16s ease;flex:0 0 auto}
.sechd:hover .sectoggle{border-color:rgba(31,92,77,.3);background:var(--accent-soft);color:var(--accent)}
.period-sec.collapsed>.sec{margin-bottom:0}
.period-sec.collapsed>.sec>.subhd,.period-sec.collapsed>.wall,.period-sec.collapsed>.daypad,.period-sec.collapsed>.sec+*,.period-sec.collapsed>div:not(.sec){display:none}
.period-sec.collapsed .sechd{border-bottom-color:var(--line);margin-bottom:0}
.period-sec.collapsed .sectoggle{transform:rotate(-90deg)}
.subhd{font-family:var(--mono);font-size:12px;color:var(--ink-faint);margin:18px 0 14px}
.wall{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;padding:0 44px}
.wall.smallwall{grid-template-columns:repeat(4,minmax(0,1fr))}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;box-shadow:var(--shadow);cursor:pointer;transition:transform .14s,border-color .14s;position:relative;min-width:0}
.card:hover{transform:translateY(-2px);border-color:var(--accent);z-index:5}
.card::before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;border-radius:8px 0 0 8px}
.card.bull::before{background:var(--bull)}.card.bear::before{background:var(--bear)}.card.neutral::before{background:var(--line-strong)}
.card.big{padding:18px 21px 16px}
.ch{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:8px 10px;padding-bottom:15px;border-bottom:1px dashed var(--line)}
.cid{display:flex;align-items:baseline;gap:2px;flex-wrap:wrap}
.hchg{margin-left:13px;display:inline-flex;align-items:baseline;gap:6px;white-space:nowrap}
.hchg-lbl{font-family:var(--mono);font-size:10px;color:var(--ink-faint)}
.cid .tk{font-family:var(--mono);font-weight:600;font-size:21px}
.cid .cur{font-family:var(--mono);font-size:9px;color:var(--gold);border:1px solid rgba(184,137,58,.5);border-radius:3px;padding:1px 5px;margin-left:6px;vertical-align:middle}
.cid .co{font-family:var(--serif);font-size:13.5px;color:var(--ink-soft);margin-top:5px;font-weight:500}
.cid .ind{font-family:var(--mono);font-size:10px;color:var(--ink-faint);margin-top:2px}
.badge{font-family:var(--serif);font-weight:700;font-size:13.5px;padding:6px 12px;border-radius:5px;white-space:nowrap}
.badge i,.stag i,.mtag i,.leg i,.ddsplit i{font-size:.9em;margin-right:4px}
.badge.bull{background:var(--bull-bg);color:var(--bull)}.badge.bear{background:var(--bear-bg);color:var(--bear)}.badge.neutral{background:var(--neutral-bg);color:var(--neutral)}
.badge.mini{font-size:10.5px;padding:3px 8px}
.countline{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap;padding-top:17px}
.tlbl{font-family:var(--mono);font-size:11px;color:var(--ink-faint)}
.tbig{font-family:var(--serif);font-weight:900;font-size:32px;color:var(--ink);line-height:1}
.tunit{font-family:var(--mono);font-size:11px;color:var(--ink-faint)}
.cfreq{font-family:var(--mono);font-size:11.5px;color:var(--ink-soft);margin-left:2px}
.cfreq b{color:var(--ink);font-weight:600}
.distrow{display:flex;align-items:baseline;gap:8px;padding-top:15px}
.dlbl{font-family:var(--mono);font-size:11px;color:var(--ink-faint);white-space:nowrap}
.dtally{font-family:var(--mono);font-size:13px;display:inline-flex;align-items:baseline;gap:4px}
.dtally b{font-size:15px;font-weight:700;line-height:1}
.dtally .u{font-size:11px;color:var(--ink-soft);margin-left:1px}
.dtally .gb{color:var(--bull)}.dtally .gr{color:var(--bear)}
.distbar{flex:1;height:7px;border-radius:4px;overflow:hidden;display:flex;background:var(--paper)}
.distbar i{display:block;height:100%}.distbar .b{background:var(--bull)}.distbar .r{background:var(--bear)}.distbar .n{background:#cfc7b2}
.distnum{font-family:var(--mono);font-size:10.5px;color:var(--ink-faint);white-space:nowrap}
.distnum .gb{color:var(--bull)}.distnum .gr{color:var(--bear)}
.csumm{font-size:12.5px;line-height:1.6;color:var(--ink-soft);margin-bottom:12px}
.aitag{font-family:var(--mono);font-size:9px;background:var(--ink);color:var(--paper);padding:2px 6px;border-radius:3px;margin-right:7px;letter-spacing:.03em;vertical-align:middle}
.cfoot{display:flex;justify-content:space-between;align-items:center;font-family:var(--mono);font-size:10.5px;color:var(--ink-faint)}
.cfoot .go{color:var(--accent);font-weight:600}
.card.small{padding:13px 15px}
.sh{display:flex;align-items:center;gap:7px;margin-bottom:6px}
.sh .tk{font-family:var(--mono);font-weight:600;font-size:15px}
.sh .cur.sm{font-family:var(--mono);font-size:8px;color:var(--gold);border:1px solid rgba(184,137,58,.5);border-radius:2px;padding:0 3px}
.sh .badge{margin-left:auto}
.sco{font-family:var(--serif);font-size:11.5px;color:var(--ink-faint);margin-bottom:7px}
.snums{font-family:var(--mono);font-size:10.5px;color:var(--ink-soft)}
@media(max-width:1280px){.wall{grid-template-columns:repeat(2,minmax(0,1fr))}.wall.smallwall{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:900px){.sidenav{width:54px}.sidenav .brand{padding-left:8px;padding-right:8px}.sidenav .glyph{width:34px;height:34px}.sidenav .bt,.sidenav .bs,.navlink span:not(.ni){display:none}.navlink .ni{display:inline}.main{margin-left:54px}.wall,.wall.smallwall{grid-template-columns:1fr;padding:0 20px}.sec{padding:24px 20px 10px}}

/* 排行榜行 */
.toplist{max-width:760px;padding:0 44px}
.trow{display:flex;align-items:center;gap:12px;padding:9px 0;border-bottom:1px dashed var(--line);cursor:pointer}
.trow:hover{background:var(--card)}
.trk{font-family:var(--serif);font-weight:900;font-size:16px;color:var(--ink-faint);width:24px;text-align:center}
.ttk{font-family:var(--mono);font-weight:600;font-size:15px;width:64px}
.tbar{flex:1;height:8px;background:var(--paper);border-radius:4px;overflow:hidden}
.tbar i{display:block;height:100%;background:var(--accent)}
.tn{font-family:var(--mono);font-size:13px;color:var(--ink);font-weight:600;width:40px;text-align:right}
.badge.mini{font-size:9.5px;padding:2px 6px;border-radius:3px}
/* 立场变化 */
.shifts{padding:0 44px;display:flex;flex-direction:column;gap:10px;max-width:600px}
.shift{display:flex;align-items:center;gap:12px;background:var(--card);border:1px solid var(--line);border-left:3px solid var(--bear);border-radius:6px;padding:13px 18px;cursor:pointer;box-shadow:var(--shadow)}
.shift:hover{transform:translateY(-2px)}
.stk{font-family:var(--mono);font-weight:600;font-size:17px}
.sfrom{font-family:var(--mono);font-size:13px;color:var(--bull);text-decoration:line-through;opacity:.7}
.sarrow{color:var(--ink-faint)}
.sto{font-family:var(--serif);font-weight:700;font-size:15px;padding:3px 10px;border-radius:4px}
.sto.bear{background:var(--bear-bg);color:var(--bear)}.sto.bull{background:var(--bull-bg);color:var(--bull)}
.sgo{margin-left:auto;font-family:var(--mono);font-size:11px;color:var(--accent)}
.empty{color:var(--ink-faint);font-family:var(--mono);font-size:13px;padding:10px 44px}
/* 季报主题演变 */
.qblock{padding:0 44px;max-width:820px;margin-bottom:24px}
.qbt{font-family:var(--serif);font-weight:700;font-size:17px;margin-bottom:6px}
.qbs{font-family:var(--mono);font-size:11px;color:var(--ink-faint);margin-bottom:14px}
.evrow{display:flex;align-items:center;gap:12px;margin-bottom:8px}
.evmo{font-family:var(--mono);font-size:12px;color:var(--ink-soft);width:80px}
.evbar{flex:1;height:22px;border-radius:5px;overflow:hidden;display:flex;border:1px solid var(--line)}
.evbar i{display:block;height:100%}
.evtot{font-family:var(--mono);font-size:11px;color:var(--ink-faint);width:46px;text-align:right}
.qlegend{display:flex;gap:16px;flex-wrap:wrap;margin-top:12px;font-family:var(--mono);font-size:11px;color:var(--ink-soft)}
.qlegend .lg i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:middle}
/* 季报多空总览 */
.qoverview{display:flex;gap:18px;padding:0 44px;max-width:820px;margin-bottom:8px;flex-wrap:wrap}
.qov{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:18px 24px;box-shadow:var(--shadow);flex:1;min-width:160px}
.qov .k{font-family:var(--mono);font-size:11px;color:var(--ink-faint);margin-bottom:8px}
.qov .v{font-family:var(--serif);font-weight:900;font-size:30px}
.qov .v.bull{color:var(--bull)}.qov .v.bear{color:var(--bear)}
.qbigbar{height:30px;border-radius:6px;overflow:hidden;display:flex;border:1px solid var(--line);margin:0 44px 6px;max-width:820px}
.qbigbar i{display:flex;align-items:center;justify-content:center;font-family:var(--mono);font-size:12px;color:#fff;font-weight:600}
/* 季报多头空头 */
.qbulls{display:flex;gap:10px;flex-wrap:wrap;padding:0 44px;max-width:820px}
.qb{background:var(--bull-bg);border:1px solid #cfe3d6;border-radius:6px;padding:10px 16px;cursor:pointer;display:flex;flex-direction:column;gap:3px}
.qb:hover{transform:translateY(-2px)}
.qb.bear{background:var(--bear-bg);border-color:#e8cfc9}
.qb .qtk{font-family:var(--mono);font-weight:600;font-size:15px;color:var(--bull)}
.qb.bear .qtk{color:var(--bear)}
.qb .qn{font-family:var(--mono);font-size:10.5px;color:var(--ink-soft)}
.secsub{font-family:var(--serif);font-weight:700;font-size:16px;padding:0 44px;margin:22px 0 4px;color:var(--ink)}

.period-sec{scroll-margin-top:20px}
html{scroll-behavior:smooth}

.cols2{display:grid;grid-template-columns:1.15fr .85fr;gap:30px;padding:0 44px;align-items:start;max-width:1400px}
.cols2 .colblock{min-width:0}
.cols3{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;padding:0 44px;max-width:1400px;align-items:start}
.toplist{padding:0}
.shifts{padding:0;max-width:none}
.qblock{padding:0 44px;max-width:1400px}
.qoverview{max-width:1400px}
.qbigbar{max-width:1356px}
.evbar{max-width:none}
.colhd{font-family:var(--serif);font-weight:700;font-size:16px;margin-bottom:12px;color:var(--ink);display:flex;align-items:center;gap:7px}
.panel{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:18px 20px;box-shadow:var(--shadow)}
.qcol{}
.qcol .colhd{margin-bottom:10px}
@media(max-width:1100px){.cols2{grid-template-columns:1fr}.cols3{grid-template-columns:1fr}}

/* ===== 二级页:个股详情 ===== */
#ddPage{display:none;position:fixed;inset:0;z-index:200;background:var(--paper);overflow-y:auto}
#ddBody{max-width:1360px;margin:0 auto;padding:24px 40px 90px}
.ddhead{display:block;padding-bottom:0;margin-bottom:0}
.ddhl{min-width:0;max-width:980px}
.ddback{display:inline-flex;align-items:center;gap:7px;margin-bottom:14px;border:1px solid var(--line);background:transparent;color:var(--ink-faint);border-radius:999px;padding:6px 10px;font-family:var(--mono);font-size:11px;font-weight:800;text-decoration:none;cursor:pointer}
.ddback:hover{color:var(--accent);border-color:rgba(31,92,77,.28);background:var(--accent-soft)}
.ddback i{font-size:10px}
.ddtk{font-family:var(--mono);font-weight:800;font-size:30px;color:var(--ink);line-height:1.05;display:flex;align-items:center;flex-wrap:wrap;gap:7px 8px}
.ddtk .market.detail,.ddtk .theme.detail{margin-left:0;transform:none}
.theme-cn{font-family:var(--sans);font-size:12px;font-weight:600;color:var(--ink-soft);margin-left:6px;vertical-align:middle}
.ddco{font-size:13px;color:var(--ink-soft);margin-top:8px;line-height:1.55;max-width:820px}.ddind{color:var(--ink-faint)}
.ddpills{margin-top:11px}
.ddpill{font-size:11px;padding:3px 11px;border-radius:11px;font-weight:600}
.ddpill.bull{background:var(--bull-bg);color:var(--bull)}.ddpill.bear{background:var(--bear-bg);color:var(--bear)}.ddpill.cw{background:#f3e7cc;color:#8a6a1f}.ddpill.neutral{background:var(--card);color:var(--ink-soft);border:1px solid var(--line)}
.ddmeta{display:flex;align-items:center;flex-wrap:wrap;gap:9px 17px;margin-top:17px;font-family:var(--mono);font-size:11.5px;color:var(--ink-faint);text-align:left;line-height:1.5}.ddmeta b{color:var(--ink);font-size:12.5px}
.ddmi{display:inline-flex;align-items:baseline;gap:6px;white-space:nowrap}.ddmi i{font-style:normal;color:var(--ink-soft);font-family:var(--sans);font-weight:650}
.ddsplit{display:inline-flex;align-items:center;gap:8px;color:var(--ink-soft)}.tup{color:var(--bull)}.tdn{color:var(--bear)}.tnt{color:var(--ink-faint)}
.ddfreq{display:inline-flex;align-items:center;gap:12px}
.ddfreq .fc{display:inline-flex;align-items:baseline;gap:4px}.ddfreq .fc i{font-style:normal;font-size:11px;color:var(--ink-soft);font-family:var(--sans);font-weight:650}.ddfreq .fc b{font-size:13px;color:var(--ink)}
.ddrel{margin:20px 0 18px;padding:0 0 16px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:8px;flex-wrap:wrap;color:var(--ink-faint);font-size:12px}
.ddrel-label{font-family:var(--mono);font-size:10.5px;font-weight:800;color:var(--ink-soft);letter-spacing:.02em}
.ddrel button{display:inline-flex;align-items:center;gap:5px;border:1px solid var(--line);border-radius:999px;background:var(--card);color:var(--ink-soft);font-family:var(--mono);font-size:11px;font-weight:800;padding:5px 9px;cursor:pointer}
.ddrel button:hover{border-color:rgba(31,92,77,.32);background:var(--accent-soft);color:var(--accent)}
.ddrel .mini-market{font-size:8.5px;font-weight:800;color:var(--ink-faint);border:1px solid var(--line);border-radius:999px;padding:0 4px;line-height:1.35}
.ddrel .mini-memo{font-size:8.5px;font-weight:850;color:var(--accent);border:1px solid rgba(31,92,77,.24);background:var(--accent-soft);border-radius:999px;padding:0 5px;line-height:1.35}
.ddmemo-missing{margin:18px 0 16px;border:1px dashed rgba(31,92,77,.28);border-radius:8px;background:rgba(31,92,77,.035);padding:14px 16px;color:var(--ink-soft)}
.ddmemo-missing b{display:flex;align-items:center;gap:7px;color:var(--ink);font-size:14px;margin-bottom:5px}
.ddmemo-missing p{font-size:12.5px;line-height:1.65;margin:0}
@media(max-width:600px){
  .main>.crumb{padding:16px 20px 0}
  .ddhead{padding-bottom:4px}
  .ddtk{font-size:27px;gap:6px}
  .ddco{font-size:12.5px;line-height:1.5}
  .ddpills{margin-top:9px}
  .ddmeta{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px 12px;margin-top:15px;font-size:11px}
  .ddmi{display:flex;justify-content:space-between;gap:8px;min-width:0}
  .ddsplit,.ddfreq{grid-column:1/-1}
  .ddsplit{line-height:1.7;flex-wrap:wrap}
  .ddfreq{justify-content:flex-start;gap:16px;flex-wrap:wrap}
  .ddrel{gap:7px;margin-bottom:16px;padding-bottom:14px}
  .ddrel-label{flex:0 0 100%}
  .ddrel button{font-size:10.5px;padding:5px 8px}
}
.ddchart{margin:18px 0 8px}.cc-svg{position:relative;width:100%;height:220px}
.charttitle{margin:22px 0 8px}
.charttitle h3{font-family:var(--serif);font-size:17px;font-weight:800;color:var(--ink);line-height:1.3}
.charttitle p{font-size:12px;color:var(--ink-faint);margin-top:4px}
.cdot{position:absolute;width:11px;height:11px;border-radius:50%;border:2px solid var(--paper);transform:translate(-50%,-50%);cursor:pointer;box-shadow:0 0 0 1px rgba(0,0,0,.15)}
.cc-leg{display:flex;gap:16px;align-items:center;flex-wrap:wrap;font-size:11.5px;color:var(--ink-soft);margin-top:8px}.cc-leg i{width:10px;height:10px;border-radius:50%;display:inline-block;margin-right:4px;vertical-align:middle}.cc-leg .g{color:var(--ink-faint)}
.ddchart-ph{padding:22px;text-align:center;color:var(--ink-faint);font-size:13px;border:1px dashed var(--line-strong);border-radius:6px;margin:18px 0 8px}
.thesis{margin:18px 0 24px;border:1px solid var(--line);border-radius:8px;background:var(--card);box-shadow:var(--shadow);padding:22px 24px}
.updates{position:relative;margin:18px 0 18px;border:1px solid rgba(31,92,77,.22);border-left:0;border-radius:8px;background:linear-gradient(90deg,rgba(31,92,77,.08),rgba(31,92,77,.025) 38%,var(--card) 100%);box-shadow:0 10px 28px -24px rgba(31,92,77,.7);padding:0;overflow:hidden}
.updates::before{content:"";position:absolute;left:0;top:0;bottom:0;width:5px;background:var(--accent)}
.updates summary{list-style:none;cursor:pointer;padding:16px 18px 16px 22px}
.updates summary::-webkit-details-marker{display:none}
.updates-top{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:8px}
.updates-k{display:inline-flex;align-items:center;gap:6px;font-family:var(--mono);font-size:11px;font-weight:800;color:var(--accent);letter-spacing:.02em}
.updates h2{font-family:var(--serif);font-size:20px;font-weight:900;line-height:1.28;color:var(--ink);margin-bottom:8px;max-width:980px}
.updates-meta{display:flex;flex-wrap:wrap;gap:8px;margin:0}
.upill{font-family:var(--mono);font-size:10.5px;font-weight:700;border-radius:999px;padding:4px 8px;background:var(--paper);border:1px solid var(--line);color:var(--ink-soft)}
.upill.high{background:#1f5c4d;color:#fff;border-color:#1f5c4d}
.updates p{font-size:14px;line-height:1.8;color:var(--ink-soft);margin:8px 0}
.updates summary p{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.updates-body{border-top:1px solid rgba(31,92,77,.18);background:var(--card);padding:0 18px 18px}
.updates ul{margin:0 0 0 18px;padding-top:12px;color:var(--ink-soft)}
.updates li{font-size:14px;line-height:1.75;margin:5px 0}
.update-more{font-family:var(--mono);font-size:11px;font-weight:800;color:var(--accent);display:inline-flex;align-items:center;gap:5px;margin-top:8px}
.updates[open] .update-more{display:none}
.thesis-kicker{font-family:var(--mono);font-size:11px;font-weight:700;color:var(--accent);letter-spacing:.02em;margin-bottom:9px}
.thesis-title{font-family:var(--serif);font-size:25px;font-weight:900;line-height:1.25;color:var(--ink);margin-bottom:8px}
.thesis-sub{font-size:14px;line-height:1.7;color:var(--ink-soft);max-width:920px}
.thesis-core{display:inline-flex;margin-top:14px;font-family:var(--mono);font-size:12px;color:var(--ink);background:var(--paper);border:1px solid var(--line);border-radius:6px;padding:7px 10px}
.thesis-summary{margin-top:16px;padding:14px 16px;border-left:3px solid var(--accent);background:var(--paper);font-size:14px;line-height:1.8;color:var(--ink)}
.thesis-sec{border-top:1px solid var(--line);padding-top:18px;margin-top:18px}
.thesis-sec h3{font-family:var(--serif);font-size:17px;font-weight:800;line-height:1.35;margin-bottom:10px;color:var(--ink)}
.thesis-sec p{font-size:14px;line-height:1.85;color:var(--ink-soft);margin:9px 0}
.jargon{position:relative;display:inline;color:var(--ink);border-bottom:1px dotted var(--accent);cursor:help}
.jargon-tip{display:none;position:absolute;left:0;bottom:135%;z-index:40;width:max-content;max-width:320px;background:var(--ink);color:var(--paper);font-size:11.5px;font-weight:400;line-height:1.55;border-radius:6px;padding:9px 11px;box-shadow:0 8px 24px -12px rgba(0,0,0,.5)}
.jargon-tip::after{content:"";position:absolute;left:12px;top:100%;border:6px solid transparent;border-top-color:var(--ink)}
.jargon.open .jargon-tip{display:block}
.thesis-cites{display:flex;flex-wrap:wrap;gap:8px;margin-top:11px}
.rcite{font-family:var(--mono);font-size:10.5px;color:var(--accent);text-decoration:none;border:1px solid var(--line);background:var(--paper);border-radius:999px;padding:5px 9px}
.rcite:hover{border-color:var(--accent);background:var(--accent-soft)}
.tweetrefs{display:grid;gap:12px;margin-top:14px}
.tweetcard{display:block;text-decoration:none;color:inherit;border:1px solid var(--line);border-radius:10px;background:#050505;box-shadow:0 0 0 1px rgba(255,255,255,.04),0 8px 22px -16px rgba(0,0,0,.75);padding:15px 16px}
.tweetcard:hover{border-color:rgba(29,155,240,.55)}
.twhead{display:flex;align-items:center;gap:9px;margin-bottom:9px;color:#f7f9f9}
.twav{width:36px;height:36px;border-radius:50%;object-fit:cover;flex:none}
.twnm{font-size:14px;font-weight:800;line-height:1;color:#f7f9f9}
.twmeta{font-family:var(--sans);font-size:13px;color:#71767b;margin-top:2px}
.twopen{margin-left:auto;color:#71767b;font-size:14px}
.tweetcard:hover .twopen{color:#1d9bf0}
.twtext{font-size:14.5px;line-height:1.55;color:#e7e9ea;white-space:pre-wrap;word-break:break-word;padding-left:45px}
.twtext .cashtag{color:#1d9bf0}
.twmore{display:inline-block;margin-top:2px;color:#1d9bf0;font-weight:500}
.tweetcard .pmedia{margin-left:45px;max-width:520px;grid-template-columns:repeat(2,minmax(0,1fr))}
.tweetcard .pmedia.one{max-width:420px;grid-template-columns:1fr}
.tweetcard .pmedia img{border-color:#2f3336;background:#16181c}
@media(max-width:760px){.tweetcard{padding:13px}.twtext,.tweetcard .pmedia{padding-left:0;margin-left:0}.twav{width:32px;height:32px}}
.thesis-final{margin-top:20px;border-top:1px solid var(--line);padding-top:16px}
.thesis-final h3{font-family:var(--serif);font-size:17px;font-weight:800;margin-bottom:8px}
.thesis-final p{font-size:14px;line-height:1.85;color:var(--ink-soft);margin:8px 0}
.ddsec{font-family:var(--serif);font-weight:700;font-size:16px;color:var(--ink);margin:28px 0 12px}.ddsec.sm{font-size:14px;margin:0 0 10px}.ddsec span{font-weight:400;font-size:11.5px;color:var(--ink-faint);margin-left:6px}
.hzrow{display:flex;gap:10px;flex-wrap:wrap}
.hz{flex:1;min-width:88px;border:1px solid var(--line);border-radius:7px;padding:10px 8px;text-align:center;background:var(--card)}
.hz .k{font-size:11px;color:var(--ink-soft)}.hz .v{font-family:var(--mono);font-weight:700;font-size:15px;margin-top:5px}.hz .v.pos{color:var(--bull)}.hz .v.neg{color:var(--bear)}.hz .v.na{color:var(--ink-faint)}
.ddcols{display:grid;grid-template-columns:1fr 1fr;gap:26px}@media(max-width:760px){.ddcols{grid-template-columns:1fr}}
.rlist{list-style:none;margin:0;padding:0}
.rlist li{display:flex;gap:8px;align-items:flex-start;font-size:13px;line-height:1.55;padding:8px 0;border-bottom:1px dashed var(--line)}
.rlist .rb{color:var(--ink-faint)}.rlist .rt{flex:1;color:var(--ink)}
.rlist .rsrc{font-family:var(--mono);font-size:10.5px;color:var(--accent);text-decoration:none;white-space:nowrap}
.rlist li.empty{color:var(--ink-faint);font-style:italic;border-bottom:none}
.post{border:1px solid var(--line);border-radius:8px;padding:12px 14px;margin-bottom:10px;background:var(--card)}
.post .ph{display:flex;align-items:center;gap:10px;margin-bottom:7px}
.post .pd{font-family:var(--mono);font-size:11px;color:var(--ink-soft)}
.post .ptag{font-size:10px;padding:1px 8px;border-radius:9px;font-weight:600}.ptag.bullish{background:var(--bull-bg);color:var(--bull)}.ptag.bearish{background:var(--bear-bg);color:var(--bear)}.ptag.neutral,.ptag.meta{background:var(--card);color:var(--ink-soft);border:1px solid var(--line)}
.post .plk{margin-left:auto;font-family:var(--mono);font-size:10.5px;color:var(--accent);text-decoration:none;white-space:nowrap}
.post .pt{font-size:13.5px;line-height:1.62;color:var(--ink);white-space:pre-wrap;word-break:break-word}
.post .peng{display:flex;gap:15px;margin-top:9px;font-family:var(--mono);font-size:10.5px;color:var(--ink-faint)}
.ddmore{text-align:center;font-size:13px;color:var(--accent);cursor:pointer;padding:13px;border:1px dashed var(--line-strong);border-radius:6px;margin-top:16px}.ddmore:hover{background:var(--card)}
.dddisc{font-size:11.5px;color:var(--ink-faint);line-height:1.7;border-top:1px solid var(--line);margin-top:32px;padding-top:14px}
.ddph{padding:50px;text-align:center;color:var(--ink-faint)}

/* 理由/风险:重设计为两块面板(#4) */
.rcols{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:26px}@media(max-width:820px){.rcols{grid-template-columns:1fr}}
.rpanel{border:1px solid var(--line);border-top:3px solid var(--line);border-radius:10px;background:var(--card);padding:0 18px 8px}
.rpanel.bull{border-top-color:var(--bull)}.rpanel.bear{border-top-color:var(--bear)}
.rph{display:flex;align-items:center;gap:8px;font-family:var(--serif);font-weight:700;font-size:15px;color:var(--ink);padding:14px 0 4px}
.rpdot{width:9px;height:9px;border-radius:50%;flex:none}.rpdot.bull{background:var(--bull)}.rpdot.bear{background:var(--bear)}
.rph .rpn{margin-left:auto;font-family:inherit;font-weight:400;font-size:11px;color:var(--ink-faint)}
.rlist .rdot{width:6px;height:6px;border-radius:50%;margin-top:8px;flex:none}.rlist .rdot.bull{background:var(--bull)}.rlist .rdot.bear{background:var(--bear)}
/* 全部发言:第三张图式紧凑行(#5) */
.postsbar{display:flex;align-items:center;gap:12px;margin:32px 0 4px;flex-wrap:wrap}
.postsbar h3{font-family:var(--serif);font-size:17px;font-weight:800;color:var(--ink);line-height:1.3;margin-right:auto}
.postcount{background:var(--ink);color:var(--paper);font-family:var(--mono);font-size:12.5px;font-weight:600;padding:5px 15px;border-radius:18px}
.postsnote{font-size:11.5px;color:var(--ink-faint)}
.plist{border-top:1px solid var(--line)}
.prow{display:grid;grid-template-columns:90px 92px 82px minmax(0,1fr);align-items:flex-start;gap:14px;padding:13px 6px;border-bottom:1px solid var(--line);text-decoration:none}
.prow.hidden{display:none}
.prow:hover{background:var(--card)}
.prd{font-family:var(--mono);font-size:11.5px;color:var(--ink-faint);padding-top:2px}
.prtag{font-size:10.5px;font-weight:600;padding:2px 9px;border-radius:9px;text-align:center;box-sizing:border-box;width:100%}
.prtag.bullish{background:var(--bull-bg);color:var(--bull)}.prtag.bearish{background:var(--bear-bg);color:var(--bear)}.prtag.neutral,.prtag.meta{background:var(--paper);color:var(--ink-soft);border:1px solid var(--line)}
.prtag.first{background:#efe7d4;color:#8a6a1f}
.prtag.ghost{visibility:hidden}
.prtx{flex:1;font-size:13.5px;line-height:1.6;color:var(--ink);white-space:pre-wrap;word-break:break-word}
.prlk{color:var(--accent);font-family:var(--mono)}
.cashtag{color:#1d9bf0;font-weight:600}
.prmore{display:inline-block;margin-left:4px;color:var(--accent);font-family:var(--mono);font-size:12px;font-weight:600}
.pmedia{display:grid;grid-template-columns:repeat(2,minmax(0,180px));gap:8px;margin-top:10px;max-width:380px}
.pmedia img{display:block;width:100%;aspect-ratio:16/10;object-fit:cover;border-radius:8px;border:1px solid var(--line);background:var(--paper)}
.pmedia.one{grid-template-columns:minmax(0,260px);max-width:260px}.pmedia.one img{aspect-ratio:16/10}
@media(max-width:760px){.prow{grid-template-columns:82px 92px minmax(0,1fr);gap:7px 10px}.prtag.first{grid-column:3}.prtx{grid-column:1/-1}}
@media(max-width:600px){
  #ddBody{padding:16px 14px 72px}
  .ddhead{gap:12px;padding-bottom:14px}
  .ddhl,.ddmeta{width:100%}
  .ddtk{font-size:28px;gap:7px}
  .ddco{line-height:1.45}
  .ddmeta{text-align:left;line-height:1.75}
  .ddfreq{justify-content:flex-start;gap:18px}
  .thesis{padding:18px 16px;margin-top:16px}
  .thesis-title{font-size:22px}
  .thesis-core{display:flex;width:100%;line-height:1.55}
  .jargon-tip{position:fixed;left:16px;right:16px;top:18%;bottom:auto;width:auto;max-width:none}
  .jargon-tip::after{display:none}
  .postsbar{align-items:flex-start}
}

</style>'''

def build():
    head=BASE_HEAD+SHARED_CSS   # 基础头已内嵌,render 完全自给,无需任何外部 html
    head=head.replace('@aleabitoreddit 个股评论追踪',f'@{PROFILE_HANDLE} — {PROFILE_NAME}')
    nav=f'''<nav class="sidenav"><div class="brand"><img class="glyph" src="{html.escape(PROFILE_AVATAR)}" alt="{html.escape(PROFILE_NAME)} avatar"><div class="bt">{html.escape(PROFILE_NAME)}</div><div class="bs"><a href="{html.escape(PROFILE_X_URL)}" target="_blank" rel="noopener">@{html.escape(PROFILE_HANDLE)}</a></div></div>
<a class="navlink on" data-t="reports"><span>{t('nav_reports')}</span><span class="ni">論</span></a>
<a class="navlink" data-t="day"><span>{t('nav_day')}</span><span class="ni">日</span></a>
<a class="navlink" data-t="week"><span>{t('nav_week')}</span><span class="ni">週</span></a>
<a class="navlink" data-t="month"><span>{t('nav_month')}</span><span class="ni">月</span></a>
<a class="navlink" data-t="quarter"><span>{t('nav_quarter')}</span><span class="ni">季</span></a></nav>'''
    secs=reports_section()
    secs+=period_section(DAYCFG)+period_section(WKCFG)
    secs+=month_section()
    secs+=quarter_section()
    JS_KEYS=['stance_bull','stance_bear','stance_neutral','stance_mixed','stance_none',
      'chart_ph_no_series','chart_dot_tip','chart_leg_bull','chart_leg_bear','chart_leg_note',
      'dd_ph_title','dd_ph_body','post_initial','dd_view_all',
      'dd_first_mention','dd_last_mention','dd_total','dd_first_px','dd_today','freq_7d','freq_28d',
      'dd_reasons_bull','dd_reasons_risk','dd_newest_first','dd_no_bull','dd_no_risk',
      'dd_all_posts','dd_posts_meta','dd_show_more','count_unit']
    i18n_js='<script>var I18N='+json.dumps({k:t(k) for k in JS_KEYS},ensure_ascii=False)+';function I(k,o){var s=I18N[k]||k;if(o)for(var p in o)s=s.split("{"+p+"}").join(o[p]);return s;}</script>'
    script='''<script>
const links=[...document.querySelectorAll('.navlink')];
function sectionStateKey(id){return 'serenity-section-collapsed:'+id;}
function setSectionCollapsed(sec,collapsed){
  sec.classList.toggle('collapsed',collapsed);
  var btn=sec.querySelector('.sectoggle');
  if(btn){
    btn.setAttribute('aria-expanded',collapsed?'false':'true');
    btn.setAttribute('title',collapsed?'展開':'收合');
  }
  try{localStorage.setItem(sectionStateKey(sec.id),collapsed?'1':'0');}catch(e){}
}
document.querySelectorAll('.period-sec').forEach(function(sec){
  var hd=sec.querySelector('.sechd');
  var title=sec.querySelector('.sechd .st');
  if(!hd)return;
  var btn=document.createElement('button');
  btn.type='button';btn.className='sectoggle';btn.setAttribute('aria-label','收合 / 展開');
  btn.innerHTML='<i class="fa-solid fa-chevron-down"></i>';
  btn.addEventListener('click',function(e){e.preventDefault();e.stopPropagation();setSectionCollapsed(sec,!sec.classList.contains('collapsed'));});
  if(title)title.insertBefore(btn,title.firstChild);
  hd.addEventListener('click',function(e){
    if(e.target.closest('.sn'))return;
    setSectionCollapsed(sec,!sec.classList.contains('collapsed'));
  });
  var collapsed=false;
  try{collapsed=localStorage.getItem(sectionStateKey(sec.id))==='1';}catch(e){}
  setSectionCollapsed(sec,collapsed);
});
links.forEach(l=>l.addEventListener('click',e=>{e.preventDefault();const t=document.getElementById(l.dataset.t);if(t){if(t.classList.contains('collapsed'))setSectionCollapsed(t,false);t.scrollIntoView({behavior:'smooth',block:'start'});}}));
const secs=links.map(l=>document.getElementById(l.dataset.t));
const obs=new IntersectionObserver(es=>{es.forEach(en=>{if(en.isIntersecting){links.forEach(l=>l.classList.toggle('on',l.dataset.t===en.target.id));}});},{rootMargin:'-30% 0px -60% 0px'});
secs.forEach(x=>x&&obs.observe(x));
function decodeEntities(t){var el=document.createElement('textarea');el.innerHTML=t==null?'':String(t);return el.value;}
function esc(t){return decodeEntities(t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
const GLOSSARY=[
  ['hyperscaler','超大規模雲端服務商，像 Amazon、Microsoft、Google 這類自建大型資料中心的公司。'],['hyperscalers','超大規模雲端服務商，像 Amazon、Microsoft、Google 這類自建大型資料中心的公司。'],
  ['ASIC','ASIC (Application Specific Integrated Circuit) 特殊應用積體電路 - 為特定用途客製化設計的晶片，常用於 AI 推論、雲端運算或專用硬體。'],['ASICs','ASIC (Application Specific Integrated Circuit) 特殊應用積體電路 - 為特定用途客製化設計的晶片，常用於 AI 推論、雲端運算或專用硬體。'],
  ['photonics','光子學 - 用光來傳輸、處理或運算訊號的技術。'],['optical interconnects','光互連 - 用光取代電訊號，在晶片、伺服器或資料中心之間高速傳輸資料。'],
  ['optical module','光模組 - 把電訊號和光訊號互相轉換的通訊元件。'],['optical modules','光模組 - 把電訊號和光訊號互相轉換的通訊元件。'],
  ['transceiver','收發器 - 同時負責發送與接收訊號的光通訊模組。'],['transceivers','收發器 - 同時負責發送與接收訊號的光通訊模組。'],
  ['laser','雷射 - 用來產生高集中度光束的元件，是光通訊供應鏈的核心零件之一。'],['CW laser','CW laser (Continuous Wave Laser) 連續波雷射 - 持續輸出穩定光源的雷射，常用於 CPO 或矽光子系統。'],['CW DFB','CW DFB (Continuous Wave Distributed Feedback) 連續波分佈回饋雷射 - 適合提供穩定單波長光源，是矽光子與 CPO 架構常被討論的雷射類型。'],['DFB','DFB (Distributed Feedback) 分佈回饋雷射 - 可輸出穩定波長的半導體雷射，常用於高速光通訊。'],['EML','EML (Electro-absorption Modulated Laser) 電吸收調變雷射 - 高速光通訊常用的雷射類型。'],
  ['InP','InP (Indium Phosphide) 磷化銦 - 適合製造高速光電與雷射元件的化合物半導體材料。'],['800G','800G - 每秒 800Gbps 的光通訊速度，是 AI 資料中心常見升級方向。'],['1.6T','1.6T - 每秒 1.6Tbps 的光通訊速度，約為 800G 的兩倍。'],
  ['silicon photonics','矽光子 - 在矽晶片平台上整合光學元件，用光來傳輸資料。'],['SiPh','SiPh (Silicon Photonics) 矽光子 - 在矽晶片平台上整合光學元件，用光來傳輸資料。'],['CPO','CPO (Co-Packaged Optics) 共同封裝光學 - 把光學元件放到更靠近晶片的位置，降低功耗並提高頻寬。'],['NPO','NPO (Near-Packaged Optics) 近封裝光學 - 光學元件非常靠近晶片，但不一定完全共同封裝。'],['pluggable','可插拔光模組 - 可以像零件一樣插拔更換的光通訊模組。'],
  ['supply chain','供應鏈 - 從材料、零件、製造到交付客戶的整個產業鏈。'],['bottleneck','瓶頸 - 限制整個系統產能或成長速度的關鍵限制。'],['chokepoint','關鍵卡點 - 供應稀缺且難以替代的環節，通常具有較高議價能力。'],
  ['TAM','TAM (Total Addressable Market) 總潛在市場規模 - 一個產品或技術理論上可以服務的最大市場。'],['LTA','LTA (Long-Term Agreement) 長期供應協議 - 客戶與供應商提前鎖定未來產能或供貨條件的合約。'],['volume ramp','量產爬坡 - 產品從小量出貨逐步擴大到大規模量產的過程。']
  ,['revenue ramp','收入爬坡 - 新產品或新客戶開始放量，收入快速增加的階段。'],['optical engines','光引擎 - 把雷射、調變與光訊號處理整合起來的核心光通訊元件。'],['ELS','ELS (External Laser Source) 外部光源 - 把雷射光源放在主要晶片或模組外部，再把光導入系統的設計。'],['NRE','NRE (Non-Recurring Engineering) 一次性工程開發費 - 為特定客戶或產品開發前期設計、驗證所產生的非重複收入。']
];
const GLOSS_MAP=Object.fromEntries(GLOSSARY.map(function(x){return [x[0].toLowerCase(),x[1]];}));
const GLOSS_RE=new RegExp('\\\\b('+GLOSSARY.map(function(x){return x[0].replace(/[.*+?^${}()|[\\]\\\\]/g,'\\\\$&');}).sort(function(a,b){return b.length-a.length;}).join('|')+')\\\\b','gi');
function glossText(t){return esc(t).replace(GLOSS_RE,function(m){var d=GLOSS_MAP[m.toLowerCase()];return '<span class="jargon" role="button" tabindex="0">'+m+'<span class="jargon-tip">'+esc(d)+'</span></span>';});}
function fmtPostText(t){return esc(t).replace(/(^|[^A-Za-z0-9_$])([$][A-Za-z0-9][A-Za-z0-9]{0,14})(?=$|[^A-Za-z0-9])/g,'$1<span class="cashtag">$2</span>');}
function shortPostText(t,limit){t=decodeEntities(t||'').trim();limit=limit||280;if(t.length<=limit)return {text:t,cut:false};var cut=t.slice(0,limit),i=Math.max(cut.lastIndexOf(' '),cut.lastIndexOf('\\n'));if(i>limit*0.72)cut=cut.slice(0,i);return {text:cut.trim(),cut:true};}
function mediaHtml(items){items=(items||[]).filter(function(m){return m&&m.type==='photo'&&m.url;});if(!items.length)return '';var cls='pmedia '+(items.length===1?'one':'');return '<div class="'+cls+'">'+items.slice(0,4).map(function(m){return '<img loading="lazy" src="'+esc(m.url)+'" alt="'+esc(m.alt_text||'Post image')+'">';}).join('')+'</div>';}
function fmtN(n){if(n==null)return '';n=+n;if(n>=1e6)return (n/1e6).toFixed(1)+'M';if(n>=1000)return (n/1000).toFixed(1)+'k';return ''+n;}
var ddOpenTicker=null;
function hashTicker(){
  var m=(location.hash||'').match(/^#ticker=(.+)$/);
  return m?decodeURIComponent(m[1]):'';
}
function tickerHash(tk){return '#ticker='+encodeURIComponent(tk);}
function hideDD(){document.getElementById('ddPage').style.display='none';document.body.style.overflow='';ddOpenTicker=null;}
function openDD(){var p=document.getElementById('ddPage');p.style.display='block';p.scrollTop=0;document.body.style.overflow='hidden';}
function closeDD(){
  if(hashTicker()){
    if(history.state&&history.state.ticker){history.back();}
    else{history.replaceState(null,'',location.pathname+location.search);hideDD();}
  }else hideDD();
}
function ddHome(){
  history.replaceState(null,'',location.pathname+location.search);
  hideDD();
  window.scrollTo({top:0,behavior:'smooth'});
}
function ddMore(b){
  var r=document.getElementById('ddRest');if(!r)return;
  var hidden=[...r.querySelectorAll('.prow.hidden')];
  hidden.slice(0,10).forEach(function(x){x.classList.remove('hidden');});
  var left=r.querySelectorAll('.prow.hidden').length;
  if(left)b.innerHTML=b.getAttribute('data-zh')==='1'?'查看更多貼文 ('+left+') <i class="fa-solid fa-chevron-down"></i>':I('dd_view_all',{n:left});else b.style.display='none';
}
function ddChart(d,zh){
  if(d.otc||!d.series||d.series.length<2) return '<div class="ddchart-ph">'+I18N.chart_ph_no_series+'</div>';
  var W=760,H=220,P=16,s=d.series,cs=s.map(function(p){return p.c;});
  var d0=Date.parse(s[0].d),dN=Date.parse(s[s.length-1].d),dsp=(dN-d0)||1;
  var _dotMax=(d.dots||[]).reduce(function(mx,m){var t=Date.parse(m.d);return t>mx?t:mx;},dN);
  if(_dotMax>dN){dN=_dotMax;dsp=(dN-d0)||1;}
  var mn=Math.min.apply(null,cs),mx=Math.max.apply(null,cs),sp=(mx-mn)||1;
  var X=function(t){return P+((t-d0)/dsp)*(W-2*P);},Y=function(v){return H-P-((v-mn)/sp)*(H-2*P);};
  var sx=s.map(function(p){return Date.parse(p.d);});
  var lineC=function(t){if(t<=sx[0])return s[0].c;if(t>=sx[sx.length-1])return s[s.length-1].c;for(var i=0;i<sx.length-1;i++){if(t>=sx[i]&&t<=sx[i+1]){var f=(sx[i+1]-sx[i])?(t-sx[i])/(sx[i+1]-sx[i]):0;return s[i].c+(s[i+1].c-s[i].c)*f;}}return s[s.length-1].c;};
  var pts=s.map(function(p){return X(Date.parse(p.d)).toFixed(1)+','+Y(p.c).toFixed(1);});
  if(_dotMax>Date.parse(s[s.length-1].d)){pts.push(X(_dotMax).toFixed(1)+','+Y(s[s.length-1].c).toFixed(1));}
  var line='M'+pts.join(' L'),area='M'+X(d0).toFixed(1)+','+H+' L'+pts.join(' L')+' L'+X(dN).toFixed(1)+','+H+' Z';
  var dots=(d.dots||[]).map(function(m){
    var t=Date.parse(m.d),xp=(X(t)/W*100).toFixed(2),yp=(Y(lineC(t))/H*100).toFixed(2);
    var col=m.s==='bear'?'var(--bear)':m.s==='bull'?'var(--bull)':'#b9b099',lbl=m.s==='bear'?(zh?'看空':I18N.stance_bear):m.s==='bull'?(zh?'看多':I18N.stance_bull):(zh?'中性':I18N.stance_neutral);
    var tip=zh?(m.d+' · '+lbl+'時提及 · 收盤 '+m.c):I('chart_dot_tip',{date:m.d,stance:lbl,c:m.c});
    return '<span class="cdot" style="left:'+xp+'%;top:'+yp+'%;background:'+col+'" title="'+tip+'"></span>';
  }).join('');
  var legBull=zh?'看多時提及':I18N.chart_leg_bull,legBear=zh?'看空時提及':I18N.chart_leg_bear,legNote=zh?'':I18N.chart_leg_note;
  return '<div class="ddchart"><div class="cc-svg"><svg viewBox="0 0 '+W+' '+H+'" width="100%" height="220" preserveAspectRatio="none"><defs><linearGradient id="ddfill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#1f7a4d" stop-opacity="0.14"/><stop offset="100%" stop-color="#1f7a4d" stop-opacity="0"/></linearGradient></defs><path d="'+area+'" fill="url(#ddfill)"/><path d="'+line+'" fill="none" stroke="#1f7a4d" stroke-width="2"/></svg>'+dots+'</div><div class="cc-leg"><span><i style="background:var(--bull)"></i>'+legBull+'</span><span><i style="background:var(--bear)"></i>'+legBear+'</span>'+(legNote?'<span class="g">'+legNote+'</span>':'')+'</div></div>';
}
function reportHtml(r,postMap,tk){
  if(!r)return '';
  function paras(a){return (a||[]).map(function(p){return '<p>'+glossText(p)+'</p>';}).join('');}
  function tweetCard(c){
    var p=postMap&&postMap[c.tweet_id];
    if(!p)return '<a class="rcite" href="'+esc(c.url||'#')+'" target="_blank" rel="noopener">'+esc(c.date||'')+' · '+esc(c.label||c.tweet_id||'source')+' <i class="fa-solid fa-arrow-up-right-from-square"></i></a>';
    var sp=shortPostText(p.text,280),more=sp.cut?'\\n<span class="twmore">閱讀更多</span>':'';
    return '<a class="tweetcard" href="'+esc(p.url||c.url||'#')+'" target="_blank" rel="noopener"><div class="twhead"><img class="twav" src="'+esc(PROFILE.avatar)+'" alt="'+esc(PROFILE.name)+' avatar"><div><div class="twnm">'+esc(PROFILE.name)+' <i class="fa-solid fa-circle-check" style="color:#1d9bf0;font-size:12px"></i></div><div class="twmeta">@'+esc(PROFILE.handle)+' · '+esc(p.d||c.date||'')+'</div></div><span class="twopen"><i class="fa-solid fa-arrow-up-right-from-square"></i></span></div><div class="twtext">'+fmtPostText(sp.text)+more+'</div>'+mediaHtml(p.media)+'</a>';
  }
  function cites(a){if(!a||!a.length)return '';var cards=[],chips=[];a.forEach(function(c){var h=tweetCard(c);if(h.indexOf('tweetcard')>=0)cards.push(h);else chips.push(h);});return (cards.length?'<div class="tweetrefs">'+cards+'</div>':'')+(chips.length?'<div class="thesis-cites">'+chips.join('')+'</div>':'');}
  function updateHtml(){
    var updates=r.updates||[];if(!updates.length)return '';
    return updates.map(function(u,idx){
    var stance={still_bullish:'仍偏多',more_bullish:'更加看多',more_cautious:'轉為謹慎',thesis_changed:'論點改變',bearish_reversal:'轉為看空',new_catalyst:'新增催化',new_risk:'新增風險'}[u.stance]||u.stance||'更新';
    var imp={high:'重要更新',medium:'一般更新',low:'小更新'}[u.importance]||u.importance||'更新';
    var genDate=(r.generated_at||'').slice(0,10),updateLabel=u.label||(idx>0?'歷史更新':((u.date&&genDate&&u.date<genDate)?'重要歷史立場更新':'最新更新'));
    var src=(u.source_tweet_ids||[]).map(function(id){var p=postMap&&postMap[id];return {tweet_id:id,date:p&&p.d,url:p&&p.url,label:PROFILE.name+' 原文'};});
    var bullets=(u.bullets||[]).map(function(b){return '<li>'+glossText(b)+'</li>';}).join('');
    return '<details class="updates"><summary><div class="updates-top"><div class="updates-k"><i class="fa-solid fa-file-lines"></i>'+updateLabel+' · '+esc(u.date||'')+'</div><div class="updates-meta"><span class="upill high">'+esc(imp)+'</span><span class="upill">'+esc(stance)+'</span></div></div><h2>'+glossText(u.title||'')+'</h2>'+paras([u.summary||''])+'<span class="update-more">展開更新內容 <i class="fa-solid fa-chevron-down"></i></span></summary><div class="updates-body">'+(bullets?'<ul>'+bullets+'</ul>':'')+cites(src)+'</div></details>';
    }).join('');
  }
  var secs=(r.sections||[]).map(function(s){return '<section class="thesis-sec"><h3>'+esc(s.heading||'')+'</h3>'+paras(s.body)+cites(s.citations)+'</section>';}).join('');
  var summary=paras(r.one_minute_summary);
  var final=paras(r.final_takeaway);
  return updateHtml()+'<article class="thesis"><div class="thesis-kicker">SERENITY $'+esc(tk)+' 投資論點</div><h2 class="thesis-title">'+glossText(r.title||'')+'</h2><div class="thesis-sub">'+glossText(r.subtitle||'')+'</div>'+(r.core_label?'<div class="thesis-core">'+glossText(r.core_label)+'</div>':'')+(summary?'<div class="thesis-summary">'+summary+'</div>':'')+secs+(final?'<section class="thesis-final"><h3>最後結論</h3>'+final+'</section>':'')+'</article>';
}
function renderDD(tk){
  var d=window.DD_DATA&&DD_DATA[tk];
  if(!d){document.getElementById('ddBody').innerHTML='<div class="ddph"><div style="font-size:18px;color:var(--ink);margin-bottom:10px">'+I('dd_ph_title',{tk:tk})+'</div><div style="font-size:13px;line-height:1.7">'+I18N.dd_ph_body+'</div></div>';ddOpenTicker=tk;openDD();return;}
  var zh=!!d.report;
  var Z={bull:'看多',bear:'看空',neutral:'中性',mixed:'多空混合',none:'僅提及',first:'首次提及',last:'最近提及',total:'總提及',firstPx:'首次提及價格',today:'今日',bullCase:'看多理由',risks:'提到的風險',newest:'最新在前',initial:'初始觀點',background:'背景',analogy:'類比',quote:'引用',mention:'提及',showMore:'查看更多貼文'};
  var industryZh={'Optical Modules':'光通訊模組','Optical Comms':'光通訊','AI Cloud/GPU':'AI 雲端 / GPU','AI Photonics/CPO Lasers':'AI 光子學 / CPO 雷射','InP Substrates':'磷化銦基板','AI Chips':'AI 晶片','Hyperscaler':'超大規模雲端服務商','SOI Wafers':'SOI 晶圓','Wafer Foundry':'晶圓代工','Compound Semiconductors':'化合物半導體'};
  var themeZh={'InP substrates':'磷化銦基板 (InP substrates)','CPO':'CPO','HBM':'HBM','Power':'電力 (Power)','Cooling':'散熱 (Cooling)','Networking':'網路互連 (Networking)','AI cloud':'AI 雲端 (AI cloud)','Custom silicon':'客製化晶片 (Custom silicon)','Other':'Other'};
  var industryText=zh&&industryZh[d.industry]?industryZh[d.industry]+' ('+esc(d.industry)+')':esc(d.industry||'');
  var themeText=zh&&themeZh[d.theme]?themeZh[d.theme]:esc(d.theme||'Other');
  var pill=d.stance==='bull'?'<span class="ddpill bull">'+(zh?Z.bull:I18N.stance_bull)+'</span>':d.stance==='bear'?'<span class="ddpill bear">'+(zh?Z.bear:I18N.stance_bear)+'</span>':d.stance==='shift'?'<span class="ddpill cw">'+(zh?Z.mixed:I18N.stance_mixed)+'</span>':d.stance==='none'?'<span class="ddpill neutral">'+(zh?Z.none:I18N.stance_none)+'</span>':'<span class="ddpill neutral">'+(zh?Z.neutral:I18N.stance_neutral)+'</span>';
  var split='<span class="tup"><i class="fa-solid fa-caret-up"></i></span>'+d.bull+' '+(zh?Z.bull:I18N.stance_bull)+' · <span class="tdn"><i class="fa-solid fa-caret-down"></i></span>'+d.bear+' '+(zh?Z.bear:I18N.stance_bear)+' · <span class="tnt"><i class="fa-solid fa-circle"></i></span>'+d.neu+' '+(zh?Z.neutral:I18N.stance_neutral);
  function zhReasonText(s){if(AUTO_REASON_TRANSLATIONS&&AUTO_REASON_TRANSLATIONS[s])return AUTO_REASON_TRANSLATIONS[s];var m={
    'laser companies are his personal favorites':'Serenity 最偏好的方向是雷射公司',
    'huge revenue expansion potential beyond lasers into full optical modules, optical engines, and ELS components':'除了雷射之外，完整光通訊模組 (optical modules)、光引擎與 ELS 元件都有很大的收入擴張潛力',
    'most revenue ramp starts in H1/H2 2027, still very early stage':'多數收入爬坡 (volume ramp) 會從 2027 上半年 / 下半年開始，目前仍屬早期階段',
    'CW laser bottleneck play':'連續波雷射 (CW laser) 瓶頸題材',
    'limited independent Western supply chain capacity':'西方獨立供應鏈 (supply chain) 產能有限',
    'CW laser chokepoint is invaluable':'連續波雷射 (CW laser) 關鍵卡點 (chokepoint) 價值很高',
    'owns the stock':'Serenity 自己持有該股',
    'scarce laser capacity that AMD and other hyperscalers are looking for':'AMD 與其他超大規模雲端服務商 (hyperscalers) 正在尋找的稀缺雷射產能',
    'US transceiver supply chain for mass production of 800g/1.6T, largest in America':'美國收發器 (transceiver) 供應鏈 (supply chain)，可支援 800G / 1.6T 量產，且規模為美國最大',
    '$600m dilution ongoing caps upside':'仍有 6 億美元稀釋壓力，可能限制短期上行空間',
    '$600m ATM causes a lot of near term pressure':'6 億美元 ATM 增發造成短期壓力',
    'extreme pluggable exposure':'對可插拔光模組 (pluggable) 曝險很高',
    'debating if CPO helps them more than it hurts':'仍需判斷共同封裝光學 (CPO) 對公司是利多大於利空，還是反過來',
    'InP CW DFB laser maker':'InP CW DFB 雷射製造商',
    'next $LITE for CPO/silicon photonics':'Serenity 認為它可能是 CPO / 矽光子 (silicon photonics) 時代的下一個 $LITE',
    'supplies lasers to POET Starlight and Ayar SuperNova':'供應雷射給 POET Starlight 與 Ayar SuperNova',
    'valued at $140M vs POET at 11x more':'當時市值約 1.4 億美元，但 $POET 估值高出約 11 倍',
    'undiscovered by institutions':'機構投資人仍未充分發現',
    '$453M pipeline next few years':'未來幾年有約 4.53 億美元 pipeline',
    'refinanced debt to $17M total':'已完成再融資，總債務約 1,700 萬美元',
    'WIN Semi foundry qualification in progress for volume production':'Win Semi 代工 qualification 進行中，有助於未來量產',
    'pure play InP laser segment for silicon photonics + CPO':'純粹的 InP 雷射業務，對應矽光子 (silicon photonics) 與 CPO',
    'Lidar segment ramping with $53-138M projected revenue':'LiDAR 業務也在爬坡，預估收入約 5,300 萬至 1.38 億美元',
    'undiscovered by institutions due to Stockholm listing':'因為在 Stockholm 上市，許多機構還沒有充分覆蓋',
    'cw dfb laser supplier to Ayar and POET and other CPO companies':'Ayar、POET 與其他 CPO 公司所需的 CW DFB 雷射供應商',
    'capital rotating into silicon photonics/CPO makes timing right':'資金開始輪動到矽光子 (silicon photonics) / CPO，時機變得更有利',
    'the next LITE for CPO/Silicon photonics':'CPO / 矽光子 (silicon photonics) 週期裡的下一個 $LITE 類型標的',
    'new choice':'Serenity 新選出的重點標的',
    'could be the next $LITE for silicon photonics/CPO':'可能成為矽光子 (silicon photonics) / CPO 領域的下一個 $LITE',
    'sits in the CW DFB laser bottleneck of next gen photonic architectures':'位在下一代光子架構的 CW DFB 雷射瓶頸',
    'laser supplier to Ayar, POET, and likely other silicon photonics/CPO players':'供應雷射給 Ayar、POET，以及其他可能的矽光子 / CPO 玩家',
    'Win semi ongoing qualification allows them to scale up capacity':'Win Semi qualification 若完成，可幫助 SIVE 擴大量產能力',
    'widely undiscovered name':'市場仍普遍沒有發現這個標的',
    'personal bull case scenario is $10 billion+':'Serenity 個人 bull case 是 100 億美元以上市值',
    'should deserve a much higher valuation than POET':'Serenity 認為它應該比 $POET 享有更高估值',
    'does the lasers for silicon photonics/CPO but is 1/6th the valuation of POET and 1/20th the valuation of Ayar':'它做的是矽光子 / CPO 所需雷射，但估值遠低於 $POET 與 Ayar',
    'InP CW DFB laser exposure for new photonics architectural shift':'提供下一代光子架構轉換所需的 InP CW DFB 雷射曝險',
    'supplies POET/Ayar/other CPO companies':'供應 POET、Ayar 與其他 CPO 公司',
    'early enough to tailor custom lasers to fit specifications before they got popular':'很早就能依客戶規格客製雷射，早於這些架構變熱門之前',
    'potential Win Semi qualification offsets volume risks':'潛在 Win Semi qualification 可降低量產風險',
    'personal CW DFB laser exposure for rotation from EML to SiPh cycle':'Serenity 用它作為從 EML 週期輪動到 SiPh / CW DFB 週期的個人曝險',
    'long term holding':'Serenity 表示偏長期持有',
    'laser supplier to up and coming CPO/silicon photonics companies':'供應雷射給正在崛起的 CPO / 矽光子公司',
    'waiting for mass order ramp':'等待大量訂單與量產爬坡',
    'thesis validation as InP CW DFB laser array supplier for silicon photonics CPO':'作為矽光子 / CPO 的 InP CW DFB 雷射陣列供應商， thesis 獲得驗證',
    'major partnership with O-Net and Enablence for CPO':'與 O-Net、Enablence 的 CPO 重大合作',
    'looks like the early $LITE for CPO/Silicon photonics at $212M valuation which looks absurd':'以約 2.12 億美元估值來看，像是早期的 CPO / 矽光子 $LITE，Serenity 認為估值很不合理',
    'laser supplier for Asian CPO supply chain via Enablence -> O-Net for AI DCs':'透過 Enablence → O-Net 供應亞洲 AI data center CPO 供應鏈所需雷射',
    'laser supplier for US hyperscaler supply chains via POET -> MRVL Celestial':'透過 POET → MRVL Celestial 進入美國 hyperscaler 供應鏈',
    'laser supplier to NVDA-backed Ayar for merchant models':'供應雷射給 NVDA 投資的 Ayar，對應 merchant model',
    'risk reward looks extremely promising':'Serenity 認為風險報酬非常有吸引力',
    'captures rotation from EML to SiPh/CW DFB architectural change':'捕捉從 EML 到 SiPh / CW DFB 架構轉換的輪動',
    'hasn\\'t been re-rated yet':'尚未完成估值重估',
    'CPO TAM exponential growth':'CPO TAM 可能呈指數級成長',
    'highest upside potential':'Serenity 認為上行潛力最高',
    'chokepoint in AI photonics supply chain':'AI photonics 供應鏈裡的關鍵瓶頸',
    'CPO/silicon photonics paradigm shift':'CPO / 矽光子架構轉換',
    'upstream laser supplier in CPO supply chain':'CPO 供應鏈裡的上游雷射供應商',
    'high potential beneficiary':'高潛力受益者',
    'used for light sources in scale up and laser arrays':'用於量產擴張與雷射陣列的光源',
    'extremely undiscovered opportunity':'市場仍極度低估、尚未充分發現的機會',
    'supplies POET and Ayar':'供應 POET 與 Ayar',
    'wins in both captive and merchant models':'在 captive 與 merchant 模式中都有機會受益',
    'CPO/Silicon photonics is main growth engine past 2027':'2027 年後主要成長引擎是 CPO / 矽光子',
    'laser company for hyperscaler photonic supply chains':'hyperscaler 光子供應鏈裡的雷射公司',
    'makes silicon photonics/CPO scale up & scale out work':'幫助矽光子 / CPO 完成 scale up 與 scale out',
    'has actual revenue':'已經有實際收入，不是純概念公司',
    'most undervalued and unknown photonics company on the market':'Serenity 認為它是市場上最被低估、最不知名的 photonics 公司之一',
    'extreme TAM expansion from AI':'AI 帶來極大的 TAM 擴張',
    'Win semi qualification is critical':'Win Semi qualification 是關鍵',
    'fabless through Win Semi so capex is lightweight':'透過 Win Semi 採 fabless 模式，資本支出較輕',
    'doesn\\'t see much downside risk long run aside from dilution':'除稀釋外，Serenity 認為長期下行風險相對有限',
    'light source for many customers rather than one':'不是只服務單一客戶，而是多個客戶的光源供應商',
    'likely guess for AMD large purchase agreements for CW lasers':'Serenity 推測 AMD 可能會簽下大型 CW laser 採購協議',
    'AMD + GFS/Sivers reference laser':'AMD + GFS / Sivers reference laser 可能形成重要供應鏈線索',
    'hopes it becomes an American company':'Serenity 希望它未來能變成更偏美國市場的公司',
    'affected by regional Swedish market liquidity':'受瑞典本地市場流動性影響',
    'main concern is laser multi-sourcing':'主要風險是客戶可能採用多來源雷射供應',
    'he doesn\\'t know anything about it yet':'Serenity 當時還不了解 $SIVE',
    'he says by derivative of POET not being a big name, Sivers likely wouldn\\'t be a major player':'她當時認為若 $POET 也不是大玩家，Sivers 可能也未必是主要玩家',
    'CPO ramp gets delayed':'CPO 量產爬坡延後',
    'dilution to scale up capacity to compete with $LITE and others':'為了擴產與 $LITE 等公司競爭，可能需要增發稀釋',
    '$LITE, $COHR competition on scale after $NVDA just gave them $4B':'$LITE、$COHR 在規模上競爭力強，且獲得 $NVDA 大額支持',
    'volume risks':'量產與出貨放量仍有風險',
    'execution':'執行風險',
    'materials supplier for LITE and photonics':'$LITE / photonics 的上游材料供應商',
    '$500M market cap':'當時市值約 5 億美元',
    'controls 60-70%+ of world\\'s InP substrates with SMTOY':'與 Sumitomo 一起控制全球 InP substrates 約 60-70% 以上供應',
    'InP substrates required for future AI buildout':'未來 AI buildout 需要 InP substrates',
    'entire AI industry bottlenecked by this company':'整個 AI 產業可能被這家公司所在環節卡住',
    '$700M company could become center of AI supply chain':'約 7 億美元市值公司可能成為 AI 供應鏈核心瓶頸',
    'mapped InP substrate supply chain':'已梳理 InP substrate 供應鏈',
    'tracked high purity indium pricing':'追蹤高純度 indium 價格',
    'modeled game theory around bottleneck hikes/supply shocks':'推演瓶頸漲價與供應衝擊下的賽局',
    'Reuters confirmed InP substrates can halt AI buildout':'Reuters 相關報導確認 InP substrates 可能影響 AI buildout',
    'Chinese gov risk always a consideration':'中國政府 / 出口管制風險一直需要考慮',
    'massive bottleneck for inp substrates':'InP substrates 本身存在重大瓶頸',
    'massive bottleneck for refining/precursors needed to make them':'製造 InP substrates 所需 refining / precursors 也存在重大瓶頸',
    '14th shareholder vote on 50M share increase putting people on edge':'14 日股東會將投票是否增加 5,000 萬股授權，讓市場緊張',
    'proposed 50M share dilution (70M to 120M shares)':'提議增加 5,000 萬股授權，從 7,000 萬股到 1.2 億股',
    'dilution overhang':'潛在稀釋壓力仍壓在股價上方',
    'up to $2B dilution':'潛在稀釋規模最高約 20 億美元',
    'board filing is a red flag':'董事會提出此文件本身就是紅旗',
    'would not hold if dilution passes':'若稀釋通過，Serenity 表示自己不會持有',
    'doubling the float':'幾乎等於大幅增加流通股本',
    'equity getting wiped out':'股東權益可能被嚴重稀釋',
    'smaller cap position that directionally played out well':'較小市值部位的方向判斷已經驗證',
    'mentioned at $30':'Serenity 早在約 30 美元時就提過',
    '$471m/month projections':'公司被提到有每月約 4.71 億美元的 projection',
    'lot of independent supply':'有較多獨立供應來源',
    'located in the US':'供應位置在美國',
    'bears are regarded when entire industry is laser/capacity constrained':'Serenity 認為在整個產業受雷射 / 產能限制時，空方低估了供應瓶頸',
    'InP substrate position validated by Reuters, Epiwafer company earnings, and institutions':'InP substrate thesis 已被 Reuters、Epiwafer 公司財報與機構買盤驗證',
    'mentioned at ~$13':'Serenity 早在約 13 美元附近就提過',
    'agreements with Google':'與 Google 相關協議',
    'no $6B new share dilution':'沒有 60 億美元的新股稀釋壓力',
    'much more asymmetrical upside':'Serenity 認為上行更不對稱',
    'colo model for AMZN and GOOGL through Fluidstack':'透過 Fluidstack 對接 AMZN / GOOGL 的 colo 模式',
    'positive catalyst for neocloud sector from data center energy deals':'data center 能源交易對 neocloud sector 是正面催化',
    'second-order tailwind from already secured GW capacity':'已鎖定 GW 級容量帶來第二層順風',
    'negative until less correlation with Bitcoin':'在與 Bitcoin 相關性降低前仍偏負面',
    'balance sheet had a lot of Bitcoin exposure':'資產負債表有較多 Bitcoin 曝險',
    'attachment to crypto dragged it down due to BTC balance sheets':'BTC 資產負債表讓它受 crypto 類股拖累',
    'part of broad miner sell-off across the board':'受到整體 miner 類股賣壓拖累',
    'implies $54 x 2 = $108 price target':'Serenity 用 54 美元乘以 2 推出約 108 美元目標價',
    '100-1000%+ YTD performer in his portfolio':'Serenity 提到這是她組合裡 YTD 100% 到 1000%+ 的標的之一',
    'part of his 30-stock portfolio he expects to keep going up':'被列入她認為仍可能上漲的 30 檔組合',
    '100%+ return YTD':'YTD 報酬已超過 100%',
    'hit 100-1000%+ YTD':'YTD 報酬達到 100% 到 1000%+ 區間',
    'went long and wrote thesis':'Serenity 表示自己做多並寫過 thesis',
    'Clarity Act is extremely damaging':'CLARITY Act 對 thesis 可能非常不利',
    'massive share unlock coming':'即將面臨大量股份解禁',
    'CLARITY act regulating away yield is biggest bear case':'若 CLARITY Act 壓低 yield，這是最大 bear case',
    'rate cuts + lower supply would hurt Circle':'降息加上供給下降可能傷害 Circle 收入',
    'hyperscaler buildout delay spillover benefits Neocloud segment':'超大規模雲端建設延後，可能讓需求外溢到 neocloud segment',
    'GPUs they hold have gone up in price':'它們持有的 GPU 價格上升',
    'H100s up 29%+ and A100s up 23%+ last month':'H100 上月上漲 29%+，A100 上漲 23%+',
    'incredible tailwind':'強烈順風',
    'GPU depreciation fears eased':'GPU depreciation 疑慮有所緩解',
    'tailwinds from increased capex spend across hyperscalers':'超大規模雲端服務商 capex 增加帶來順風',
    'sees bubbles forming around debt interest':'Serenity 看到債務利息周圍可能形成泡沫',
    'OpenAI contagion risk':'OpenAI 連鎖風險',
    'getting eaten alive by debt interest':'債務利息正在嚴重侵蝕公司',
    'debt interest too high':'債務利息過高',
    '$6B of constant selling pressure from the ATM':'60 億美元 ATM 帶來持續賣壓',
    'still stagnant':'股價 / thesis 仍停滯',
    '$6B ATM that needs to be bought through first':'需要先消化 60 億美元 ATM 賣壓',
    '$6B ATMs':'60 億美元 ATM 增發壓力',
    'top performer in Neoclouds/Energy segment':'Neoclouds / Energy segment 裡的 top performer',
    'triple digit YTD':'YTD 已達三位數報酬',
    'all time highs':'創歷史新高',
    'neocloud theme thesis playing out':'neocloud 主題 thesis 正在驗證',
    'reaching ATHs':'正在接近 / 創下歷史新高',
    'could end up like AWS one day':'Serenity 認為未來有機會像 AWS 一樣重要',
    'probably rangebound for Q1 due to 25M share ATM offering being tapped':'因 2,500 萬股 ATM offering 被啟用，Q1 可能區間震盪',
    'not a fan of the second ATM right after $138 convertible note funding':'Serenity 不喜歡在 1.38 億美元可轉債融資後立刻又做第二次 ATM',
    'has an active 25M share ATM running':'仍有 2,500 萬股 ATM 正在進行',
    'ATM offering a risk as management could dilute and add selling pressure':'ATM offering 是風險，管理層可能稀釋股東並增加賣壓',
    'around the same starting point as Lumentum which went from 2.88B to 67B MC in 2 years':'起點類似 Lumentum；Lumentum 曾在兩年內從 28.8 億美元市值到 670 億美元',
    'expects significant rerate if higher confidence mapping to NVDA CPO ecosystem is released':'如果釋出與 NVDA CPO ecosystem 更高信心的 mapping，Serenity 預期可能明顯 rerate',
    'laser supplier for next gen architectures, not just CPO scale up':'不只是 CPO scale up，而是下一代架構的雷射供應商',
    'Sivers and Jabil developed 1.6T optical transceivers with CW lasers designing around EML bottlenecks':'Sivers 與 Jabil 開發 1.6T optical transceivers，用 CW lasers 繞開 EML 瓶頸',
    "Jabil management says they created a 'relatively dramatic moat'":'Jabil 管理層稱其建立了「相當明顯的 moat」',
    'immediately used for next gen 1.6T pluggable transceivers':'可立即用於下一代 1.6T 可插拔 transceivers',
    'probably one of the better names to invest in':'Serenity 認為這可能是較好的投資標的之一',
    'probably better ROI than a depreciating car':'Serenity 開玩笑說，ROI 可能比折舊的車更好',
    'upstream ecosystem from hyperscaler AI buildout should go brrr':'超大規模雲端 AI buildout 的上游 ecosystem 可能持續受益',
    'pushing hard CoPoS':'TSMC 正積極推動 CoPoS',
    'VisEra/others might go brrr earlier than expected':'VisEra 等供應鏈可能比預期更早受益',
    'long idea that played out well':'長線 thesis 已經驗證得不錯',
    "doesn't see a bubble in upstream semiconductors":'Serenity 不認為上游半導體已經形成泡沫',
    'profit from buildout would be insane to make up for capex decreasing':'即使 capex 增速下降，AI buildout 帶來的利潤仍可能非常可觀',
    'InP substrate export easing relieves mass production bottlenecks':'InP substrate 出口放寬，緩解量產瓶頸',
    'part of his optical positions':'Serenity 光通訊 / photonics 部位之一',
    'core high conviction idea from 2025':'2025 年的核心高信心 idea 之一',
    'price appreciation from $330 to $904':'股價從約 330 美元上漲到 904 美元，驗證原 thesis',
    'CPO scale up optical products shipping H2 2027':'CPO scale-up optical products 預計 2027 下半年出貨',
    'formal ramp up in 2028':'正式放量預計在 2028 年',
    'no delays, aligns with previous timelines':'目前沒有延遲，與先前時程一致',
    'needs to buy the substrates':'仍需要外部採購 substrates',
    'uncertain near-term supply chain impact':'短期供應鏈影響仍不確定',
    'would lack InP to produce opticals for GOOGL TPU Ironwood':'若 InP 供應受限，可能缺少生產 GOOGL TPU Ironwood opticals 所需材料',
    'sold photonic positions short term':'Serenity 短期賣出 photonics 部位',
    'Sumitomo export controlled causing capacity issues downstream':'Sumitomo 出口管制可能造成下游產能問題',
    'sold positions at ~$385':'Serenity 約在 385 美元附近賣出部位',
    'found some potential issues in internal research':'內部研究發現一些潛在問題',
    'already priced in with a premium':'估值已經反映相當高的 premium',
    "still thinks there's upside":'Serenity 仍認為有上行空間',
    'less likely to double at current prices as fast on shares only':'以目前股價來看，單靠持股快速翻倍的機率較低',
    'gets upside from CPO as new growth vector':'CPO 作為新成長向量，仍能帶來上行空間',
    'CPO related name he likes':'Serenity 喜歡的 CPO 相關標的',
    "if Chinese suppliers stop selling 6N polycrystal, Coherent's laser and transceiver business effectively hits a wall":'如果中國供應商停止出售 6N 多晶材料，Coherent 的雷射與 transceiver 業務可能直接撞牆',
    'categorized as compounder':'被歸類為較穩健的 compounder'
  };return m[s]||s;}
  function mkR(a,empty,cls){if(!a||!a.length)return '<li class="empty">'+empty+'</li>';return a.map(function(r){return '<li><span class="rdot '+cls+'"></span><span class="rt">'+(zh?glossText(zhReasonText(r[0])):esc(r[0]))+'</span><a class="rsrc" href="'+r[1]+'" target="_blank" rel="noopener">'+r[2]+' <i class="fa-solid fa-arrow-up-right-from-square"></i></a></li>';}).join('');}
  function postTag(t){if(!zh)return t.tag;var m={'Bullish':Z.bull,'Bearish':Z.bear,'Neutral':Z.neutral,'Background':Z.background,'Analogy':Z.analogy,'Quote':Z.quote,'Mention':Z.mention};return m[t.tag]||t.tag;}
  function postRow(t,hidden){var fb=t.first?'<span class="prtag first">'+(zh?Z.initial:I18N.post_initial)+'</span>':'<span class="prtag first ghost">'+(zh?Z.initial:I18N.post_initial)+'</span>';var more=t.cut?' <span class="prmore">... '+I18N.dd_show_more+'</span>':'';return '<a class="prow '+(hidden?'hidden':'')+'" href="'+t.url+'" target="_blank" rel="noopener"><span class="prd">'+t.d+'</span><span class="prtag '+t.st+'">'+postTag(t)+'</span>'+fb+'<div class="prtx">'+fmtPostText(t.text)+more+' <span class="prlk"><i class="fa-solid fa-arrow-up-right-from-square"></i></span>'+mediaHtml(t.media)+'</div></a>';}
  function relatedHtml(){
    var pool=Object.keys(DD_DATA||{}).filter(function(s){
      if(s===tk)return false;
      var x=DD_DATA[s]||{};
      return (d.theme&&d.theme!=='Other'&&x.theme===d.theme)||(d.industry&&x.industry===d.industry);
    }).map(function(s){
      var x=DD_DATA[s]||{}, score=0;
      if(d.theme&&d.theme!=='Other'&&x.theme===d.theme)score+=10000;
      if(d.industry&&x.industry===d.industry)score+=5000;
      if(x.report)score+=1000;
      score+=(x.total||0);
      return {s:s,x:x,score:score};
    }).sort(function(a,b){return b.score-a.score;}).slice(0,7);
    if(!pool.length)return '';
    return '<div class="ddrel"><span class="ddrel-label">'+(zh?'相關標的':'Related')+'</span>'+pool.map(function(o){
      var memo=o.x.report?'<span class="mini-memo">論點</span>':'';
      return '<button type="button" onclick="dd(\\''+o.s+'\\')" title="'+esc(o.x.co||o.s)+'">'+o.s+'<span class="mini-market">'+esc(o.x.market||'')+'</span>'+memo+'</button>';
    }).join('')+'</div>';
  }
  function missingReportHtml(){
    if(d.report)return '';
    return '<div class="ddmemo-missing"><b><i class="fa-regular fa-file-lines"></i>尚未整理完整投資論點</b><p>目前先保留 '+esc(PROFILE.name)+' 的貼文、看多理由、風險與價格路徑；若訊號累積足夠，會整理成完整投資論點。</p></div>';
  }
  var firstPxTxt=d.firstPx?((d.cur?d.cur+' ':'')+d.firstPx):'—';
  var _ps=d.posts,_latest=_ps.length?_ps[0].d:null,_head=_ps.filter(function(p){return p.d===_latest;}),_rest=_ps.filter(function(p){return p.d!==_latest;});
  var postMap={};_ps.forEach(function(p){if(p.id)postMap[p.id]=p;});
  var plistHtml='<div class="plist">'+_head.map(function(p){return postRow(p,false);}).join('')+(_rest.length?'<div id="ddRest">'+_rest.map(function(p){return postRow(p,true);}).join('')+'</div>':'')+'</div>'+(_rest.length?'<div class="ddmore" '+(zh?'data-zh="1" ':'')+'onclick="ddMore(this)">'+(zh?Z.showMore+' ('+_rest.length+') <i class="fa-solid fa-chevron-down"></i>':I('dd_view_all',{n:_rest.length}))+'</div>':'');
  document.getElementById('ddBody').innerHTML=
    '<div class="ddhead"><div class="ddhl"><button class="ddback" type="button" onclick="ddHome()" aria-label="返回 '+esc(PROFILE.name)+'"><i class="fa-solid fa-arrow-left"></i><span>返回 '+esc(PROFILE.name)+'</span></button><div class="ddtk">'+tk+'<span class="market detail">'+esc(d.market||'')+'</span><span class="theme detail '+(d.theme==='Other'?'other':'')+'">'+themeText+'</span></div><div class="ddco">'+esc(d.co)+(d.industry?' · <span class="ddind">'+industryText+'</span>':'')+'</div><div class="ddpills">'+pill+'</div></div>'+
    '<div class="ddmeta"><span class="ddmi"><i>'+(zh?Z.first:I18N.dd_first_mention)+'</i><b>'+d.first+'</b></span><span class="ddmi"><i>'+(zh?Z.last:I18N.dd_last_mention)+'</i><b>'+d.last+'</b></span><span class="ddmi"><i>'+(zh?Z.total:I18N.dd_total)+'</i><b>'+d.total+(I18N.count_unit?' '+I18N.count_unit:'')+'</b></span><span class="ddmi"><i>'+(zh?Z.firstPx:I18N.dd_first_px)+'</i><b>'+firstPxTxt+'</b></span><span class="ddsplit">'+split+'</span><span class="ddfreq"><span class="fc"><i>'+(zh?Z.today:I18N.dd_today)+'</i><b>'+d.m_today+'</b></span><span class="fc"><i>'+I18N.freq_7d+'</i><b>'+d.m7+'</b></span><span class="fc"><i>'+I18N.freq_28d+'</i><b>'+d.m28+'</b></span></span></div></div>'+
    relatedHtml()+
    reportHtml(d.report,postMap,tk)+
    missingReportHtml()+
    '<div class="charttitle"><h3>'+(zh?'$'+tk+' 自 '+esc(PROFILE.name)+' 首次提及以來的股價走勢':'$'+tk+' price path since '+esc(PROFILE.name)+' first mentioned it')+'</h3><p>'+(zh?'圓點標記 '+esc(PROFILE.name)+' 發文，顏色代表立場。':'Dots mark '+esc(PROFILE.name)+' posts by inferred stance.')+'</p></div>'+
    ddChart(d,zh)+
    '<div class="rcols"><div class="rpanel bull"><div class="rph"><span class="rpdot bull"></span>'+(zh?Z.bullCase:I18N.dd_reasons_bull)+'<span class="rpn">'+(zh?Z.newest:I18N.dd_newest_first)+'</span></div><ul class="rlist">'+mkR(d.reasonsBull,I18N.dd_no_bull,'bull')+'</ul></div><div class="rpanel bear"><div class="rph"><span class="rpdot bear"></span>'+(zh?Z.risks:I18N.dd_reasons_risk)+'<span class="rpn">'+(zh?Z.newest:I18N.dd_newest_first)+'</span></div><ul class="rlist">'+mkR(d.reasonsRisk,I18N.dd_no_risk,'bear')+'</ul></div></div>'+
    '<div class="postsbar"><h3>'+(zh?'今日 $'+tk+' 貼文':'Today\\'s $'+tk+' mentions')+'</h3><span class="postcount">'+(zh?'全部 $'+tk+' 貼文 ':'All $'+tk+' posts ')+d.total+'</span></div>'+
    plistHtml+
    '';
  ddOpenTicker=tk;openDD();
}
function dd(tk){if(hashTicker()!==tk)history.pushState({ticker:tk},'',tickerHash(tk));renderDD(tk);}
function syncTickerRoute(){var tk=hashTicker();if(tk)renderDD(tk);else if(ddOpenTicker)hideDD();}
window.addEventListener('hashchange',syncTickerRoute);
window.addEventListener('popstate',syncTickerRoute);
document.addEventListener('click',function(e){
  var j=e.target.closest&&e.target.closest('.jargon');
  document.querySelectorAll('.jargon.open').forEach(function(x){if(x!==j)x.classList.remove('open');});
  if(j){e.preventDefault();e.stopPropagation();j.classList.toggle('open');}
});
document.addEventListener('keydown',function(e){
  if((e.key==='Enter'||e.key===' ')&&e.target.classList&&e.target.classList.contains('jargon')){e.preventDefault();e.target.click();}
  if(e.key==='Escape')document.querySelectorAll('.jargon.open').forEach(function(x){x.classList.remove('open');});
});
function qsort(k,th){var tb=document.getElementById('qtbl').tBodies[0];var rows=[].slice.call(tb.rows);var dir=th.getAttribute('data-dir')==='desc'?'asc':'desc';var hs=document.querySelectorAll('#qtbl th.sortable');for(var i=0;i<hs.length;i++){hs[i].setAttribute('data-dir','');hs[i].classList.remove('on');}th.setAttribute('data-dir',dir);th.classList.add('on');var asc=dir==='asc';rows.sort(function(a,b){var x=parseFloat(a.getAttribute('data-'+k)),y=parseFloat(b.getAttribute('data-'+k));var xn=isNaN(x),yn=isNaN(y);if(xn&&yn)return 0;if(xn)return 1;if(yn)return -1;return asc?x-y:y-x;});for(var j=0;j<rows.length;j++)tb.appendChild(rows[j]);}
syncTickerRoute();
</script>'''
    overlay='<div id="ddPage"><div id="ddBody"></div></div>'
    profile_js='<script>var PROFILE='+json.dumps({'slug':PROFILE_SLUG,'name':PROFILE_NAME,'handle':PROFILE_HANDLE,'xUrl':PROFILE_X_URL,'avatar':PROFILE_AVATAR},ensure_ascii=False)+';</script>'
    reason_translations_js='<script>var AUTO_REASON_TRANSLATIONS='+json.dumps(REASON_TRANSLATIONS,ensure_ascii=False)+';</script>'
    dddata='<script>var DD_DATA='+json.dumps(dd_data(),ensure_ascii=False)+';</script>'
    crumb=f'<div class="crumb"><a href="../">X Conviction</a><span class="sep">/</span><b>{html.escape(PROFILE_NAME)}</b></div>'
    body=f'<body>\n{nav}\n<div class="main">\n{crumb}\n{secs}\n</div>\n{overlay}\n{profile_js}\n{i18n_js}\n{reason_translations_js}\n{dddata}\n{script}\n</body></html>'
    suffix='' if (LANG_ARG is None or LANG=='zh') else f'-{LANG}'
    out_name=f'{PROFILE_OUTPUT_PREFIX}-{DAY.isoformat()}{suffix}.html'
    open(out_name,'w',encoding='utf-8').write(head+body)
    print('built '+os.path.abspath(out_name))

if __name__=='__main__': build()
