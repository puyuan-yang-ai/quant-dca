"""
三模型样本外(OOS)预测对比图 —— 把抽象的 AUC 变成可感知的图。

数据来源：output/oos_proba_{v3,v3_n2,v4}.csv（walk-forward 产出，无泄漏：
每个预测都来自未见过该样本的模型；训练区天然没有 OOS 预测，故只画样本外）。

主图：SPY K 线 + GT 真底(label=1, 绿方块) + 当前模型买点(proba>fold阈值)，
      买点绿=命中真底(label=1)/红=没中(label=0)。
副图：v3/v3_n2/v4 三条 OOS 概率曲线 + 各自中位阈值线。
顶部按钮切换查看哪个模型的买点；悬停看该日三模型概率/决策/GT。
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from src.interactive_chart import _serve, _ensure_chart_lib
from src.data_loader import load_data
from experiments.configs import DATA_FILE
from ml.labeling import run as run_labeling

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(ROOT, 'output')
MODELS = ['v3', 'v3_n2', 'v4']
MODEL_COLORS = {'v3': '#42A5F5', 'v3_n2': '#FF9800', 'v4': '#AB47BC'}
_HTML = 'oos_comparison.html'


def _load_oos():
    data = {}
    for m in MODELS:
        path = os.path.join(OUTPUT_DIR, f'oos_proba_{m}.csv')
        if not os.path.exists(path):
            raise FileNotFoundError(f'缺少 {path}，请先跑 python -m ml.research.compare_v3_v3n2_v4')
        df = pd.read_csv(path, parse_dates=['date'])
        df['ds'] = df['date'].dt.strftime('%Y-%m-%d')
        data[m] = df
    return data


def build_html(title='SPY OOS 三模型对比', port=9872):
    oos = _load_oos()

    # OOS 区间
    start = min(df['date'].min() for df in oos.values())
    end = max(df['date'].max() for df in oos.values())
    start_s, end_s = start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')

    raw = load_data(os.path.join(ROOT, DATA_FILE), start_s, end_s)
    candles = [{'time': d['date'], 'open': d['open'], 'high': d['high'],
                'low': d['low'], 'close': d['close']} for d in raw]

    # GT 真底（label=1，与模型目标同口径：SL7 ±2 bar；用 NDay2 候选）
    labeled = run_labeling(n_days=2, method='sl_proximity', sl_n=7, k=2)
    gt_dates = set(d.strftime('%Y-%m-%d')
                   for d in labeled[labeled['label'] == 1]['date']
                   if start_s <= d.strftime('%Y-%m-%d') <= end_s)
    gt_markers = sorted(
        [{'time': ds, 'position': 'belowBar', 'shape': 'square',
          'color': '#00E676', 'text': 'GT'} for ds in gt_dates],
        key=lambda m: m['time'])

    # 每模型：买点标记(proba>fold阈值, 按 label 着色) + 概率曲线 + 中位阈值 + 明细
    marker_sets = {}
    prob_series = []
    threshold_lines = []
    detail = {}  # ds -> {model: {proba, thr, buy, label, ret}}

    for m in MODELS:
        df = oos[m].sort_values('date')
        markers = []
        for r in df.itertuples():
            buy = r.proba > r.fold_threshold
            d = detail.setdefault(r.ds, {})
            d[m] = {'proba': round(float(r.proba), 3),
                    'thr': round(float(r.fold_threshold), 3),
                    'buy': bool(buy), 'label': int(r.label),
                    'ret': None if pd.isna(r.forward_return) else round(float(r.forward_return), 4)}
            if buy:
                hit = (r.label == 1)
                markers.append({
                    'time': r.ds, 'position': 'belowBar', 'shape': 'arrowUp',
                    'color': '#26a69a' if hit else '#ef5350',
                    'text': f'{m}{"✓" if hit else "✗"}',
                })
        marker_sets[m] = sorted(markers, key=lambda x: x['time'])
        prob_series.append({
            'name': m, 'color': MODEL_COLORS[m], 'lineWidth': 2,
            'data': [{'time': r.ds, 'value': round(float(r.proba), 4)} for r in df.itertuples()],
        })
        threshold_lines.append({
            'value': round(float(df['fold_threshold'].median()), 3),
            'color': MODEL_COLORS[m], 'label': f'{m} 阈值',
        })

    # 命中率统计（买点中命中真底的比例）
    summary = {}
    for m in MODELS:
        n_buy = len(marker_sets[m])
        n_hit = sum(1 for x in marker_sets[m] if x['text'].endswith('✓'))
        summary[m] = {'buy': n_buy, 'hit': n_hit,
                      'rate': round(100 * n_hit / n_buy, 1) if n_buy else 0.0}

    html = _render(title, candles, gt_markers, marker_sets, prob_series,
                   threshold_lines, detail, summary, start_s, end_s)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    _ensure_chart_lib(OUTPUT_DIR)
    with open(os.path.join(OUTPUT_DIR, _HTML), 'w', encoding='utf-8') as f:
        f.write(html)
    _serve(OUTPUT_DIR, port, filename=_HTML)


def _render(title, candles, gt_markers, marker_sets, prob_series,
            threshold_lines, detail, summary, start_s, end_s):
    btns = ''.join(
        f'<button id="b-{m}" class="vb" onclick="setModel(\'{m}\')">{m} '
        f'(买{summary[m]["buy"]}·命中{summary[m]["rate"]}%)</button>'
        for m in MODELS)
    return f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>{title}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;transition:background .3s,color .3s}}
body.dark{{background:#131722;color:#d1d4dc}}
body.light{{background:#fff;color:#333}}
#h{{padding:10px 16px;display:flex;align-items:center;gap:14px;flex-wrap:wrap;transition:background .3s}}
body.dark #h{{background:#1e222d;border-bottom:1px solid #2a2e39}}
body.light #h{{background:#f0f3fa;border-bottom:1px solid #d6dcde}}
#h h1{{font-size:15px}}
.st{{font-size:12px}}
body.dark .st{{color:#787b86}}
body.light .st{{color:#888}}
.vb{{cursor:pointer;border:1px solid #888;border-radius:4px;background:transparent;color:inherit;padding:3px 8px;font-size:12px}}
body.dark .vb.on{{background:#2a2e39;border-color:#d1d4dc}}
body.light .vb.on{{background:#e0e3eb;border-color:#333}}
#tg{{margin-left:auto;cursor:pointer;border:1px solid #888;border-radius:6px;background:transparent;color:inherit;padding:4px 10px}}
#c{{width:100%;height:56vh}}
#p{{width:100%;height:26vh}}
body.dark #p{{border-top:1px solid #2a2e39}}
body.light #p{{border-top:1px solid #d6dcde}}
#tip{{position:fixed;top:54px;right:16px;z-index:20;border-radius:6px;padding:8px 11px;font-size:12px;line-height:1.6;max-width:320px;display:none;pointer-events:none}}
body.dark #tip{{background:rgba(30,34,45,.96);border:1px solid #2a2e39;color:#d1d4dc}}
body.light #tip{{background:rgba(255,255,255,.97);border:1px solid #d6dcde;color:#333}}
</style></head><body class="light">
<div id="h"><h1>{title}</h1><div class="st">OOS {start_s} ~ {end_s}</div>
<div class="st">绿↑=买点命中真底 / 红↑=没中 · 绿方块=GT真底</div>{btns}
<button id="tg" onclick="toggleTheme()">&#9788;</button></div>
<div id="tip"></div><div id="c"></div><div id="p"></div>
<script src="lightweight-charts.standalone.production.js"></script>
<script>
const candles={json.dumps(candles)};
const gtMarkers={json.dumps(gt_markers, ensure_ascii=False)};
const markerSets={json.dumps(marker_sets, ensure_ascii=False)};
const probSeries={json.dumps(prob_series, ensure_ascii=False)};
const thrLines={json.dumps(threshold_lines, ensure_ascii=False)};
const detail={json.dumps(detail, ensure_ascii=False)};
const models={json.dumps(MODELS)};
const themes={{dark:{{bg:'#131722',text:'#d1d4dc',grid:'#1e222d',border:'#2a2e39'}},light:{{bg:'#ffffff',text:'#333333',grid:'#f0f0f0',border:'#d6dcde'}}}};
let curTheme=localStorage.getItem('chartTheme')||'light';
const th=themes[curTheme];
const chart=LightweightCharts.createChart(document.getElementById('c'),{{layout:{{background:{{color:th.bg}},textColor:th.text}},grid:{{vertLines:{{color:th.grid}},horzLines:{{color:th.grid}}}},timeScale:{{borderColor:th.border}},rightPriceScale:{{borderColor:th.border}}}});
const cs=chart.addCandlestickSeries({{upColor:'#26a69a',downColor:'#ef5350',borderUpColor:'#26a69a',borderDownColor:'#ef5350',wickUpColor:'#26a69a',wickDownColor:'#ef5350'}});
cs.setData(candles);
let model=models[0];
function setModel(m){{model=m;
  const all=gtMarkers.concat(markerSets[m]||[]).sort((a,b)=>a.time<b.time?-1:a.time>b.time?1:0);
  cs.setMarkers(all);
  models.forEach(x=>{{const b=document.getElementById('b-'+x);if(b)b.classList.toggle('on',x===m);}});
}}
const pc=LightweightCharts.createChart(document.getElementById('p'),{{layout:{{background:{{color:th.bg}},textColor:th.text}},grid:{{vertLines:{{color:th.grid}},horzLines:{{color:th.grid}}}},timeScale:{{borderColor:th.border}},rightPriceScale:{{borderColor:th.border,scaleMargins:{{top:0.08,bottom:0.08}}}}}});
let first=null;
probSeries.forEach(c=>{{const s=pc.addLineSeries({{color:c.color,lineWidth:c.lineWidth||2,priceLineVisible:false,lastValueVisible:true,title:c.name}});s.setData(c.data);if(!first)first=s;}});
if(first){{thrLines.forEach(l=>first.createPriceLine({{price:l.value,color:l.color,lineWidth:1,lineStyle:2,axisLabelVisible:true,title:l.label}}));}}
const tip=document.getElementById('tip');
function key(t){{if(!t)return null;if(typeof t==='string')return t;if(t.year)return t.year+'-'+String(t.month).padStart(2,'0')+'-'+String(t.day).padStart(2,'0');return null;}}
function showTip(t){{const k=key(t);const d=k?detail[k]:null;if(!d){{tip.style.display='none';return;}}
  let h='<b>'+k+'</b>';
  models.forEach(m=>{{const x=d[m];if(x){{h+='<br>'+m+': p='+x.proba+' / 阈'+x.thr+' '+(x.buy?'<b>买</b>':'不买')+' · GT'+(x.label?'<span style=\\'color:#26a69a\\'>真底</span>':'<span style=\\'color:#ef5350\\'>非底</span>')+(x.ret!=null?' · 20D '+(x.ret*100).toFixed(1)+'%':'');}}}});
  tip.innerHTML=h;tip.style.display='block';}}
let sync=false;
function sr(src,r){{if(!r||sync)return;sync=true;if(src!==chart)chart.timeScale().setVisibleRange(r);if(src!==pc)pc.timeScale().setVisibleRange(r);sync=false;}}
chart.timeScale().subscribeVisibleTimeRangeChange(r=>sr(chart,r));
pc.timeScale().subscribeVisibleTimeRangeChange(r=>sr(pc,r));
chart.subscribeCrosshairMove(p=>{{if(p.time){{pc.setCrosshairPosition(undefined,p.time,first||undefined);showTip(p.time);}}}});
pc.subscribeCrosshairMove(p=>{{if(p.time){{chart.setCrosshairPosition(undefined,p.time,cs);showTip(p.time);}}}});
chart.timeScale().fitContent();pc.timeScale().fitContent();
setModel(models[0]);
function applyTheme(t){{const c=themes[t];document.body.className=t;const o={{layout:{{background:{{color:c.bg}},textColor:c.text}},grid:{{vertLines:{{color:c.grid}},horzLines:{{color:c.grid}}}},timeScale:{{borderColor:c.border}},rightPriceScale:{{borderColor:c.border}}}};chart.applyOptions(o);pc.applyOptions(o);localStorage.setItem('chartTheme',t);document.getElementById('tg').textContent=t==='dark'?'\\u2606':'\\u2605';}}
function toggleTheme(){{curTheme=curTheme==='dark'?'light':'dark';applyTheme(curTheme);}}
window.toggleTheme=toggleTheme;
applyTheme(curTheme);
window.addEventListener('resize',()=>{{chart.applyOptions({{width:document.getElementById('c').clientWidth,height:document.getElementById('c').clientHeight}});pc.applyOptions({{width:document.getElementById('p').clientWidth,height:document.getElementById('p').clientHeight}});}});
</script></body></html>'''


def main():
    import argparse
    p = argparse.ArgumentParser(description='三模型 OOS 预测对比图')
    p.add_argument('--port', type=int, default=9872)
    args = p.parse_args()
    build_html(port=args.port)


if __name__ == '__main__':
    main()
