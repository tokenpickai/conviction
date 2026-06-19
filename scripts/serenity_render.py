import json, datetime, sys, glob, os, re
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
_db_override=_argval('--db') or os.environ.get('SERENITY_DB')
DB=str(Path(_db_override).resolve()) if _db_override else str(SCRIPT_DIR.parent/'data'/'db')
STOCK={}                       # sym -> {company, industry, currency, price_series, price_status}
REPORTS={}                     # sym -> long-form ticker research report
allm=defaultdict(list)         # sym -> [(date, stance, mention_type, reason, url), ...] (all mentions)
MENT=defaultdict(list)         # sym -> [full mention dicts] (for the per-stock detail page)
_maxdate=None
for _rf in glob.glob(str(Path(DB).parent/'reports'/'*.json')):
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

# as-of date: first positional CLI arg (YYYY-MM-DD), ignoring --flags and their values; else latest mention date
_skip=set()
for _i,_x in enumerate(sys.argv):
    if _x in ('--db','--lang') and _i+1<len(sys.argv): _skip.add(_i+1)
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

# ---- i18n: en/zh built-in; other languages loaded from SCRIPT_DIR/lang/{code}.json; default en ----
LANG=(_argval('--lang') or 'en').lower()
STR={
 'en':{
  'doc_title':"@aleabitoreddit — Serenity",'brand':"Serenity",
  'nav_day':"Daily",'nav_week':"Weekly",'nav_month':"Monthly",'nav_quarter':"Quarterly",
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
  'nav_day':"日报",'nav_week':"周报",'nav_month':"月报",'nav_quarter':"季报",
  'disc_main':"公开推文的整理与追踪,由 AI 自动归纳,可能存在错误或遗漏,不保证信息绝对准确,请以原推文为准并自行核实。本追踪不构成任何投资建议。",
  'disc_detail_top':"个股详情 · 仅整理博主的公开发言,不构成投资建议",
  'disc_chart':"仅供信息整理,不构成投资建议。",
  'q_methodology':"统计口径:博主在推文中表达的看多/看空观点(表态),非其实际持仓。",
  'stance_bull':"看多",'stance_bear':"看空",'stance_mixed':"多空并存",'stance_neutral':"中性",'stance_none':"未表态",
  'pfx_day':"今日",'pfx_week':"本周",'pfx_month':"近28日",'pfx_quarter':"近90日",
  'badge_bull':"<i class='fa-solid fa-caret-up'></i> {pfx}看多",'badge_bear':"<i class='fa-solid fa-caret-down'></i> {pfx}看空",'badge_neutral':"<i class='fa-solid fa-circle'></i> {pfx}中性",
  'badge_mixed':"<i class='fa-solid fa-rotate'></i> {pfx}多空并存",'badge_none':"<i class='fa-regular fa-circle'></i> {pfx}未表态",
  'surf_bear_n':"<i class='fa-solid fa-caret-down'></i> {pfx}看空({n}条)",'shift':"<i class='fa-solid fa-rotate'></i> 较上次表态:{a} <i class='fa-solid fa-arrow-right'></i> {b}",
  'gain_lbl':"涨幅",'chg_daily_lbl':"较上一交易日",'gain_pending':"暂未接入",'count_unit':"次",
  'tally_lbl':"{pfx}表态",'tally_bgonly':"{pfx}表态:无(仅背景提及)",'bgonly_inline':"仅作为背景提及，未表态",
  'u_bull':"多",'u_bear':"空",'u_neu':"中",
  'foot_first':"首提 {date}",'foot_first_last':"首提 {d1} · 最近 {d2}",
  'updated':"<i class='fa-regular fa-clock'></i> 数据更新 {date}",'detail_go':"详情 <i class='fa-solid fa-arrow-right'></i>",'detail':"详情",
  'gain_tip':"起 {fd} {px1} → 止 {ld} {px2}",
  'legend_stance_scroll':"| 立场={pfx}表态,窗口滚动;次数为窗口计数",
  'subhd_notable':"<i class='fa-solid fa-chevron-down'></i> {pfx}值得注意(看空 / 立场转变)",'subhd_new':"<i class='fa-solid fa-chevron-down'></i> {pfx}新出现的标的",
  'newc_line':"{pfx}首次进入视野 {n} 只(可点进二级页):",'subhd_rest':"<i class='fa-solid fa-chevron-down'></i> 其余顺带提及",
  'restc_line':"{pfx}还顺带提到 {n} 只,延续既有关注或背景提及(可点进二级页):",'chips_more':"展开剩余 {n} 只 <i class='fa-solid fa-chevron-down'></i>",
  'head_day_mentions':"当天提及",'freq_7d':"7日内",'freq_28d':"28日内",
  'subhd_day':"当天重点讨论的标的(按当天提及量)",
  'head_week_mentions':"本周提及",'freq_near7':"近7日",'freq_near28':"近28日",
  'subhd_week':"本周重点讨论的标的(按近7日提及量)",
  'sec_count':"{range} {ntk} 只标的 · {nment} 次提及",'period_none':"本期无看空或立场转变的标的。",
  'head_month_mentions':"近28日提及",'month_count':"近28日 {ntk} 只标的 · {nment} 次提及",
  'sec_count':"{range} {ntk} 只标的 · {nment} 次提及",'period_none':"本期无看空或立场转变的标的。",
  'subhd_month_top':"<i class='fa-solid fa-chevron-down'></i> 本月讨论最多的标的(按近28日提及量)与其立场分布",
  'subhd_month_new':"<i class='fa-solid fa-chevron-down'></i> 本月新增标的(首次进入视野且近28日 >=5 次)",
  'trow_month_n':"本月 {c} 次",
  'legend_new':"<i class='fa-solid fa-star'></i> 新增 = 本月首次进入视野",
  'legend_resurg':"<i class='fa-solid fa-arrow-trend-up'></i> 新活跃 = 老标的沉寂后本月重新放量(前28天 ≤2 次、本月 ≥5 次)",
  'legend_bar':"条形 = 近28日表态分布(<b class='gb'><i class='fa-solid fa-caret-up'></i> 多</b> / <b class='gr'><i class='fa-solid fa-caret-down'></i> 空</b> / <i class='fa-solid fa-circle'></i> 中)",'tag_new':"<i class='fa-solid fa-star'></i> 新增",'tag_resurg':"<i class='fa-solid fa-arrow-trend-up'></i> 新活跃",
  'quarter_count':"近90日 {n} 只标的 · {v} 次提及",
  'subhd_q_overview':"<i class='fa-solid fa-chevron-down'></i> 季度方向总览(按标的数,非表态次数)",
  'q_net_bull':"净看多标的",'q_net_bear':"净看空标的",'q_balanced':"多空持平",'q_with_stance':"有表态",
  'q_summary':"按标的数:净看多 <b class='gb'>{pbk}%</b> · 净看空 <b class='gr'>{prk}%</b>(其中纯看空 {npure} 只)　| 累计表态次数 看多 {TB} / 看空 {TR} / 中性 {TN}(次数受少数高频标的影响,故方向以标的数为准)",
  'subhd_q_table':"<i class='fa-solid fa-chevron-down'></i> 季度全标的表",
  'q_table_hint':"| 点 涨幅 / 提及次数 / 看多 / 看空 / 中性 列头可排序;近90日 ≥3 次提及({n} 只);行业空(—)=未分类",
  'th_ticker':"代码",'th_industry':"行业",'th_first':"首次提及",'th_last':"最近提及",
  'th_gain':"涨幅",'th_mentions':"提及次数",'th_bull':"看多",'th_bear':"看空",'th_neu':"中性",
  'gain_formula_tip':"涨幅 =(最近提及价 − 首提价)÷ 首提价",
  'dd_back':"← 返回",'dd_first_mention':"首次提及",'dd_last_mention':"最近提及",
  'dd_total':"总提及",'dd_first_px':"首提价",'dd_today':"今日",
  'dd_reasons_bull':"看好的理由",'dd_reasons_risk':"提到的风险",'dd_newest_first':"最新在前",
  'dd_no_bull':"(暂无明确看多理由)",'dd_no_risk':"暂未提及风险",'dd_no_detail':"暂无详情",
  'dd_all_posts':"全部发言",'dd_posts_meta':"按时间倒序 · 原文保留英文,点击跳原帖",
  'dd_show_more':"在 X 查看更多",
  'post_initial':"初始观点",
  'chart_leg_bull':"看多时提及",'chart_leg_bear':"看空时提及",
  'chart_leg_note':"圆点=提及当天(同日合并); 纵轴=收盘价(非交易日使用最近交易日收盘价)",
  'chart_dot_tip':"{date} · {stance}时提及 · 收盘 {c}",
  'chart_ph_no_series':"无连续价格数据(行情未覆盖) — 仅记录提及时间点,不绘制价格曲线",
  'chart_no_cover':"该票行情未覆盖,价格曲线有限。",
  'tag_background':"背景",'tag_comparison':"比喻",'tag_quote':"引用",'tag_mention':"提及",
  'dd_ph_title':"暂无 {tk} 的详情",
  'dd_ph_body':"该标的仅少量或背景提及,尚未形成可展开的记录。<br>点击右上角「← 返回」回到看板。",
  'dd_view_all':"查看更多帖子（剩余 {n} 条）<i class='fa-solid fa-chevron-down'></i>",
  'dd_disc_body':"本页整理的是博主的公开发言——立场、自述理由、发帖频次,以及自首次提及以来的价格走势。",
  'disc_top':"⚠️ 本页为对博主 {link} 公开推文的整理与追踪,由 AI 自动归纳,<b>可能存在错误或遗漏,不保证信息绝对准确,请以原推文为准并自行核实</b>。本追踪不构成任何投资建议。",
  'disc_top_sub':"立场标签(看多 / 看空 / 中性)由 AI 对原文的语义分析推断，可能存在误判 · 未表态 = 仅提及、未表达态度",
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
    d=(ups[0].get('date') or '')[5:] or 'new'
    return f'<span class="updchip"><i class="fa-solid fa-file-lines"></i> 報告更新 {d}</span>'
def ymd(d):return d.strftime('%Y-%m-%d') if d else '—'
def co_of(s):return STOCK.get(s,{}).get('company') or s
def ind_of(s):return STOCK.get(s,{}).get('industry') or ''
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
        def collect(want_risk,want_stance,capn):
            seen=set(); res=[]
            for m in reversed(ms):
                if m['mtype']!='explicit_stance': continue
                if want_risk is not None and m['is_risk']!=want_risk: continue
                if want_stance and m['stance']!=want_stance: continue
                for r in (m['reasons'] or []):
                    k=(r or '').strip().lower()
                    if not k or k in seen: continue
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
<div class="subhd"><i class="fa-solid fa-chevron-down"></i> {cfg['subhd']} <span style="color:var(--ink-soft);font-weight:400;font-size:12.5px">　{t('legend_stance_scroll',pfx=pfx)}</span></div></div>
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
        ind=ind_of(s) or '<span class="muted">—</span>'
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
<div class="ovnote">{t('q_methodology')}</div>
</div>
<div class="subhd" style="margin-top:28px">{t('subhd_q_table')} <span style="color:var(--ink-soft);font-weight:400;font-size:12.5px">　{t('q_table_hint',n=len(rows))}</span></div>
{table}
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
.updchip{display:inline-flex;align-items:center;gap:4px;vertical-align:middle;margin-left:6px;padding:2px 7px;border:1px solid rgba(31,92,77,.24);border-radius:999px;background:var(--accent-soft);color:var(--accent);font-family:var(--mono);font-size:9.5px;font-weight:700;line-height:1.35;white-space:nowrap}
.updchip i{font-size:9px}
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
.trow{display:grid;grid-template-columns:26px 70px 58px 175px 1fr 102px 140px 74px;align-items:center;gap:12px;padding:11px 4px;border-bottom:1px dashed var(--line);cursor:pointer}
.trow:hover{background:var(--card)}
.trow .trk,.trow .ttk,.trow .tn{width:auto}.trow .trk{text-align:center}
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
.stbl .q-dt .qpx{display:block;font-family:var(--mono);font-size:10px;color:var(--ink-faint);margin-top:2px;font-weight:400}
.qinfo{display:inline-flex;align-items:center;justify-content:center;width:14px;height:14px;font-size:12px;font-weight:400;font-style:normal;color:var(--ink-faint);cursor:help;position:relative;vertical-align:middle}
.qinfo:hover{color:var(--accent)}
.qinfo:hover::after{content:attr(data-tip);position:absolute;top:160%;left:50%;transform:translateX(-50%);width:max-content;max-width:210px;white-space:normal;text-align:center;line-height:1.5;background:var(--ink);color:var(--paper);font-size:11px;font-weight:400;letter-spacing:normal;padding:7px 11px;border-radius:6px;z-index:60;box-shadow:0 4px 14px rgba(0,0,0,.2);pointer-events:none}
.sec{padding:34px 44px 10px}
.sechd{display:flex;align-items:baseline;gap:14px;border-bottom:2px solid var(--ink);padding-bottom:12px;margin-bottom:8px}
.sechd .st{font-family:var(--serif);font-weight:900;font-size:30px}
.sechd .datepill{font-family:var(--mono);font-weight:500;font-size:13px;color:var(--ink-soft);background:transparent;padding:0;border-radius:0;letter-spacing:0}
.sechd .sn{margin-left:auto;display:flex;flex-direction:column;align-items:flex-end;gap:4px}
.sechd .sn .cnt{font-family:var(--mono);font-size:12px;color:var(--accent);background:var(--accent-soft);padding:4px 12px;border-radius:5px}
.sechd .sn .upd{font-family:var(--mono);font-size:12px;color:var(--ink-soft);font-weight:500}
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
.ddhead{display:flex;justify-content:space-between;gap:24px;flex-wrap:wrap;border-bottom:2px solid var(--ink);padding-bottom:16px;margin-bottom:6px}
.ddtk{font-family:var(--mono);font-weight:800;font-size:30px;color:var(--ink);line-height:1;display:flex;align-items:center;flex-wrap:wrap;gap:7px 8px}
.ddtk .market.detail,.ddtk .theme.detail{margin-left:0;transform:none}
.theme-cn{font-family:var(--sans);font-size:12px;font-weight:600;color:var(--ink-soft);margin-left:6px;vertical-align:middle}
.ddco{font-size:13px;color:var(--ink-soft);margin-top:7px}.ddind{color:var(--ink-faint)}
.ddpills{margin-top:11px}
.ddpill{font-size:11px;padding:3px 11px;border-radius:11px;font-weight:600}
.ddpill.bull{background:var(--bull-bg);color:var(--bull)}.ddpill.bear{background:var(--bear-bg);color:var(--bear)}.ddpill.cw{background:#f3e7cc;color:#8a6a1f}.ddpill.neutral{background:var(--card);color:var(--ink-soft);border:1px solid var(--line)}
.ddmeta{font-family:var(--mono);font-size:11.5px;color:var(--ink-faint);text-align:right;line-height:1.85}.ddmeta b{color:var(--ink)}
.ddsplit{margin-top:3px}.tup{color:var(--bull)}.tdn{color:var(--bear)}.tnt{color:var(--ink-faint)}
.ddfreq{display:flex;gap:16px;justify-content:flex-end;margin-top:9px}
.ddfreq .fc{display:flex;flex-direction:column;align-items:center}.ddfreq .fc i{font-style:normal;font-size:10px;color:var(--ink-faint)}.ddfreq .fc b{font-size:16px;color:var(--ink)}
.ddchart{margin:18px 0 8px}.cc-svg{position:relative;width:100%;height:220px}
.charttitle{margin:22px 0 8px}
.charttitle h3{font-family:var(--serif);font-size:17px;font-weight:800;color:var(--ink);line-height:1.3}
.charttitle p{font-size:12px;color:var(--ink-faint);margin-top:4px}
.cdot{position:absolute;width:11px;height:11px;border-radius:50%;border:2px solid var(--paper);transform:translate(-50%,-50%);cursor:pointer;box-shadow:0 0 0 1px rgba(0,0,0,.15)}
.cc-leg{display:flex;gap:16px;align-items:center;flex-wrap:wrap;font-size:11.5px;color:var(--ink-soft);margin-top:8px}.cc-leg i{width:10px;height:10px;border-radius:50%;display:inline-block;margin-right:4px;vertical-align:middle}.cc-leg .g{color:var(--ink-faint)}
.ddchart-ph{padding:22px;text-align:center;color:var(--ink-faint);font-size:13px;border:1px dashed var(--line-strong);border-radius:6px;margin:18px 0 8px}
.thesis{margin:18px 0 24px;border:1px solid var(--line);border-radius:8px;background:var(--card);box-shadow:var(--shadow);padding:22px 24px}
.updates{margin:18px 0 18px;border:1px solid rgba(31,92,77,.28);border-left:5px solid var(--accent);border-radius:8px;background:linear-gradient(0deg,var(--accent-soft),var(--accent-soft));box-shadow:0 1px 0 rgba(0,0,0,.04);padding:0}
.updates summary{list-style:none;cursor:pointer;padding:16px 18px}
.updates summary::-webkit-details-marker{display:none}
.updates-k{font-family:var(--mono);font-size:11px;font-weight:800;color:var(--accent);letter-spacing:.02em;margin-bottom:7px}
.updates h2{font-family:var(--serif);font-size:19px;font-weight:900;line-height:1.3;color:var(--ink);margin-bottom:7px}
.updates-meta{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 12px}
.upill{font-family:var(--mono);font-size:10.5px;font-weight:700;border-radius:999px;padding:4px 8px;background:var(--paper);border:1px solid var(--line);color:var(--ink-soft)}
.upill.high{background:var(--accent-soft);border-color:rgba(31,92,77,.25);color:var(--accent)}
.updates p{font-size:14px;line-height:1.8;color:var(--ink-soft);margin:8px 0}
.updates summary p{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.updates-body{border-top:1px solid rgba(31,92,77,.18);background:var(--card);padding:0 18px 18px}
.updates ul{margin:0 0 0 18px;padding-top:12px;color:var(--ink-soft)}
.updates li{font-size:14px;line-height:1.75;margin:5px 0}
.update-more{font-family:var(--mono);font-size:11px;font-weight:700;color:var(--accent);display:inline-flex;align-items:center;gap:5px;margin-top:8px}
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
    head=head.replace('@aleabitoreddit 个股评论追踪',t('doc_title'))
    nav=f'''<nav class="sidenav"><div class="brand"><img class="glyph" src="assets/serenity-avatar.jpg" alt="Serenity avatar"><div class="bt">{t('brand')}</div><div class="bs"><a href="https://x.com/aleabitoreddit" target="_blank" rel="noopener">@aleabitoreddit</a></div></div>
<a class="navlink on" data-t="day"><span>{t('nav_day')}</span><span class="ni">DAY</span></a>
<a class="navlink" data-t="week"><span>{t('nav_week')}</span><span class="ni">WK</span></a>
<a class="navlink" data-t="month"><span>{t('nav_month')}</span><span class="ni">MO</span></a>
<a class="navlink" data-t="quarter"><span>{t('nav_quarter')}</span><span class="ni">QTR</span></a></nav>'''
    secs=period_section(DAYCFG)+period_section(WKCFG)
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
links.forEach(l=>l.addEventListener('click',e=>{e.preventDefault();const t=document.getElementById(l.dataset.t);if(t)t.scrollIntoView({behavior:'smooth',block:'start'});}));
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
  ['laser','雷射 - 用來產生高集中度光束的元件，是光通訊供應鏈的核心零件之一。'],['CW laser','CW laser (Continuous Wave Laser) 連續波雷射 - 持續輸出穩定光源的雷射，常用於 CPO 或矽光子系統。'],['EML','EML (Electro-absorption Modulated Laser) 電吸收調變雷射 - 高速光通訊常用的雷射類型。'],
  ['InP','InP (Indium Phosphide) 磷化銦 - 適合製造高速光電與雷射元件的化合物半導體材料。'],['800G','800G - 每秒 800Gbps 的光通訊速度，是 AI 資料中心常見升級方向。'],['1.6T','1.6T - 每秒 1.6Tbps 的光通訊速度，約為 800G 的兩倍。'],
  ['CPO','CPO (Co-Packaged Optics) 共同封裝光學 - 把光學元件放到更靠近晶片的位置，降低功耗並提高頻寬。'],['NPO','NPO (Near-Packaged Optics) 近封裝光學 - 光學元件非常靠近晶片，但不一定完全共同封裝。'],['pluggable','可插拔光模組 - 可以像零件一樣插拔更換的光通訊模組。'],
  ['supply chain','供應鏈 - 從材料、零件、製造到交付客戶的整個產業鏈。'],['bottleneck','瓶頸 - 限制整個系統產能或成長速度的關鍵限制。'],['chokepoint','關鍵卡點 - 供應稀缺且難以替代的環節，通常具有較高議價能力。'],
  ['TAM','TAM (Total Addressable Market) 總潛在市場規模 - 一個產品或技術理論上可以服務的最大市場。'],['LTA','LTA (Long-Term Agreement) 長期供應協議 - 客戶與供應商提前鎖定未來產能或供貨條件的合約。'],['volume ramp','量產爬坡 - 產品從小量出貨逐步擴大到大規模量產的過程。']
  ,['revenue ramp','收入爬坡 - 新產品或新客戶開始放量，收入快速增加的階段。'],['optical engines','光引擎 - 把雷射、調變與光訊號處理整合起來的核心光通訊元件。']
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
    var sp=shortPostText(p.text,280),more=sp.cut?'\\n<span class="twmore">Read more</span>':'';
    return '<a class="tweetcard" href="'+esc(p.url||c.url||'#')+'" target="_blank" rel="noopener"><div class="twhead"><img class="twav" src="assets/serenity-avatar.jpg" alt="Serenity avatar"><div><div class="twnm">Serenity <i class="fa-solid fa-circle-check" style="color:#1d9bf0;font-size:12px"></i></div><div class="twmeta">@aleabitoreddit · '+esc(p.d||c.date||'')+'</div></div><span class="twopen"><i class="fa-solid fa-arrow-up-right-from-square"></i></span></div><div class="twtext">'+fmtPostText(sp.text)+more+'</div>'+mediaHtml(p.media)+'</a>';
  }
  function cites(a){if(!a||!a.length)return '';var cards=[],chips=[];a.forEach(function(c){var h=tweetCard(c);if(h.indexOf('tweetcard')>=0)cards.push(h);else chips.push(h);});return (cards.length?'<div class="tweetrefs">'+cards+'</div>':'')+(chips.length?'<div class="thesis-cites">'+chips.join('')+'</div>':'');}
  function updateHtml(){
    var u=(r.updates||[])[0];if(!u)return '';
    var stance={still_bullish:'仍偏多',more_bullish:'更加看多',more_cautious:'轉為謹慎',thesis_changed:'論點改變',bearish_reversal:'轉為看空',new_catalyst:'新增催化',new_risk:'新增風險'}[u.stance]||u.stance||'更新';
    var imp={high:'重要更新',medium:'一般更新',low:'小更新'}[u.importance]||u.importance||'更新';
    var src=(u.source_tweet_ids||[]).map(function(id){var p=postMap&&postMap[id];return {tweet_id:id,date:p&&p.d,url:p&&p.url,label:'Serenity 原文'};});
    var bullets=(u.bullets||[]).map(function(b){return '<li>'+glossText(b)+'</li>';}).join('');
    return '<details class="updates"><summary><div class="updates-k">最新更新 · '+esc(u.date||'')+'</div><h2>'+glossText(u.title||'')+'</h2><div class="updates-meta"><span class="upill high">'+esc(imp)+'</span><span class="upill">'+esc(stance)+'</span></div>'+paras([u.summary||''])+'<span class="update-more">展開更新內容 <i class="fa-solid fa-chevron-down"></i></span></summary><div class="updates-body">'+(bullets?'<ul>'+bullets+'</ul>':'')+cites(src)+'</div></details>';
  }
  var secs=(r.sections||[]).map(function(s){return '<section class="thesis-sec"><h3>'+glossText(s.heading||'')+'</h3>'+paras(s.body)+cites(s.citations)+'</section>';}).join('');
  var summary=paras(r.one_minute_summary);
  var final=paras(r.final_takeaway);
  return updateHtml()+'<article class="thesis"><div class="thesis-kicker">SERENITY $'+esc(tk)+' 投資論點報告</div><h2 class="thesis-title">'+glossText(r.title||'')+'</h2><div class="thesis-sub">'+glossText(r.subtitle||'')+'</div>'+(r.core_label?'<div class="thesis-core">'+glossText(r.core_label)+'</div>':'')+(summary?'<div class="thesis-summary">'+summary+'</div>':'')+secs+(final?'<section class="thesis-final"><h3>最後結論</h3>'+final+'</section>':'')+'</article>';
}
function renderDD(tk){
  var d=window.DD_DATA&&DD_DATA[tk];
  if(!d){document.getElementById('ddBody').innerHTML='<div class="ddph"><div style="font-size:18px;color:var(--ink);margin-bottom:10px">'+I('dd_ph_title',{tk:tk})+'</div><div style="font-size:13px;line-height:1.7">'+I18N.dd_ph_body+'</div></div>';ddOpenTicker=tk;openDD();return;}
  var zh=!!d.report;
  var Z={bull:'看多',bear:'看空',neutral:'中性',mixed:'多空混合',none:'僅提及',first:'首次提及',last:'最近提及',total:'總提及',firstPx:'首次提及價格',today:'今日',bullCase:'看多理由',risks:'提到的風險',newest:'最新在前',initial:'初始觀點',background:'背景',analogy:'比喻',quote:'引用',mention:'提及',showMore:'查看更多貼文'};
  var industryZh={'Optical Modules':'光通訊模組','Optical Comms':'光通訊','AI Cloud/GPU':'AI 雲端 / GPU','AI Photonics/CPO Lasers':'AI 光子學 / CPO 雷射','InP Substrates':'磷化銦基板','AI Chips':'AI 晶片','Hyperscaler':'超大規模雲端服務商','SOI Wafers':'SOI 晶圓','Wafer Foundry':'晶圓代工','Compound Semiconductors':'化合物半導體'};
  var industryText=zh&&industryZh[d.industry]?industryZh[d.industry]+' ('+esc(d.industry)+')':esc(d.industry||'');
  var pill=d.stance==='bull'?'<span class="ddpill bull">'+(zh?Z.bull:I18N.stance_bull)+'</span>':d.stance==='bear'?'<span class="ddpill bear">'+(zh?Z.bear:I18N.stance_bear)+'</span>':d.stance==='shift'?'<span class="ddpill cw">'+(zh?Z.mixed:I18N.stance_mixed)+'</span>':d.stance==='none'?'<span class="ddpill neutral">'+(zh?Z.none:I18N.stance_none)+'</span>':'<span class="ddpill neutral">'+(zh?Z.neutral:I18N.stance_neutral)+'</span>';
  var split='<span class="tup"><i class="fa-solid fa-caret-up"></i></span>'+d.bull+' '+(zh?Z.bull:I18N.stance_bull)+' · <span class="tdn"><i class="fa-solid fa-caret-down"></i></span>'+d.bear+' '+(zh?Z.bear:I18N.stance_bear)+' · <span class="tnt"><i class="fa-solid fa-circle"></i></span>'+d.neu+' '+(zh?Z.neutral:I18N.stance_neutral);
  function zhReasonText(s){var m={
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
    'debating if CPO helps them more than it hurts':'仍需判斷共同封裝光學 (CPO) 對公司是利多大於利空，還是反過來'
  };return m[s]||s;}
  function mkR(a,empty,cls){if(!a||!a.length)return '<li class="empty">'+empty+'</li>';return a.map(function(r){return '<li><span class="rdot '+cls+'"></span><span class="rt">'+(zh?glossText(zhReasonText(r[0])):esc(r[0]))+'</span><a class="rsrc" href="'+r[1]+'" target="_blank" rel="noopener">'+r[2]+' <i class="fa-solid fa-arrow-up-right-from-square"></i></a></li>';}).join('');}
  function postTag(t){if(!zh)return t.tag;var m={'Bullish':Z.bull,'Bearish':Z.bear,'Neutral':Z.neutral,'Background':Z.background,'Analogy':Z.analogy,'Quote':Z.quote,'Mention':Z.mention};return m[t.tag]||t.tag;}
  function postRow(t,hidden){var fb=t.first?'<span class="prtag first">'+(zh?Z.initial:I18N.post_initial)+'</span>':'<span class="prtag first ghost">'+(zh?Z.initial:I18N.post_initial)+'</span>';var more=t.cut?' <span class="prmore">... '+I18N.dd_show_more+'</span>':'';return '<a class="prow '+(hidden?'hidden':'')+'" href="'+t.url+'" target="_blank" rel="noopener"><span class="prd">'+t.d+'</span><span class="prtag '+t.st+'">'+postTag(t)+'</span>'+fb+'<div class="prtx">'+fmtPostText(t.text)+more+' <span class="prlk"><i class="fa-solid fa-arrow-up-right-from-square"></i></span>'+mediaHtml(t.media)+'</div></a>';}
  var firstPxTxt=d.firstPx?((d.cur?d.cur+' ':'')+d.firstPx):'—';
  var _ps=d.posts,_latest=_ps.length?_ps[0].d:null,_head=_ps.filter(function(p){return p.d===_latest;}),_rest=_ps.filter(function(p){return p.d!==_latest;});
  var postMap={};_ps.forEach(function(p){if(p.id)postMap[p.id]=p;});
  var plistHtml='<div class="plist">'+_head.map(function(p){return postRow(p,false);}).join('')+(_rest.length?'<div id="ddRest">'+_rest.map(function(p){return postRow(p,true);}).join('')+'</div>':'')+'</div>'+(_rest.length?'<div class="ddmore" '+(zh?'data-zh="1" ':'')+'onclick="ddMore(this)">'+(zh?Z.showMore+' ('+_rest.length+') <i class="fa-solid fa-chevron-down"></i>':I('dd_view_all',{n:_rest.length}))+'</div>':'');
  document.getElementById('ddBody').innerHTML=
    '<div class="ddhead"><div class="ddhl"><div class="ddtk">'+tk+'<span class="market detail">'+esc(d.market||'')+'</span><span class="theme detail '+(d.theme==='Other'?'other':'')+'">'+esc(d.theme||'Other')+'</span></div><div class="ddco">'+esc(d.co)+(d.industry?' · <span class="ddind">'+industryText+'</span>':'')+'</div><div class="ddpills">'+pill+'</div></div>'+
    '<div class="ddmeta"><div class="ddmrow">'+(zh?Z.first:I18N.dd_first_mention)+' <b>'+d.first+'</b>　·　'+(zh?Z.last:I18N.dd_last_mention)+' <b>'+d.last+'</b></div><div class="ddmrow">'+(zh?Z.total:I18N.dd_total)+' <b>'+d.total+'</b>'+(I18N.count_unit?' '+I18N.count_unit:'')+'　·　'+(zh?Z.firstPx:I18N.dd_first_px)+' <b>'+firstPxTxt+'</b></div><div class="ddsplit">'+split+'</div><div class="ddfreq"><span class="fc"><i>'+(zh?Z.today:I18N.dd_today)+'</i><b>'+d.m_today+'</b></span><span class="fc"><i>'+I18N.freq_7d+'</i><b>'+d.m7+'</b></span><span class="fc"><i>'+I18N.freq_28d+'</i><b>'+d.m28+'</b></span></div></div></div>'+
    reportHtml(d.report,postMap,tk)+
    '<div class="charttitle"><h3>'+(zh?'$'+tk+' 自 Serenity 首次提及以來的股價走勢':'$'+tk+' price path since Serenity first mentioned it')+'</h3><p>'+(zh?'圓點標記 Serenity 發文，顏色代表立場。':'Dots mark Serenity posts by inferred stance.')+'</p></div>'+
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
    dddata='<script>var DD_DATA='+json.dumps(dd_data(),ensure_ascii=False)+';</script>'
    body=f'<body>\n{nav}\n<div class="main">\n{secs}\n</div>\n{overlay}\n{i18n_js}\n{dddata}\n{script}\n</body></html>'
    out_name=f'serenity-tracker-{DAY.isoformat()}{"" if LANG=="en" else "-"+LANG}.html'
    open(out_name,'w',encoding='utf-8').write(head+body)
    print('built '+os.path.abspath(out_name))

if __name__=='__main__': build()
