"""
生成空间 GT walk-forward OOS 人工审核图表。

输出为本地静态 HTML，审核结果保存在浏览器 localStorage，并可导出/导入 JSON。
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ml.research.eval_spatial_detection import run as run_detection
from src.indicators import calc_ema
from src.interactive_chart import _ensure_chart_lib, _serve

ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = ROOT / "output"
REVIEW_CSV = OUTPUT_DIR / "spatial_gt_detection_review.csv"
SUMMARY_CSV = OUTPUT_DIR / "spatial_gt_detection_summary.csv"
META_JSON = OUTPUT_DIR / "spatial_gt_detection_meta.json"
DEFAULT_FILENAME = "spatial_gt_human_review.html"


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _build_payload():
    if not REVIEW_CSV.exists() or not SUMMARY_CSV.exists() or not META_JSON.exists():
        run_detection()

    review = pd.read_csv(REVIEW_CSV)
    summary = pd.read_csv(SUMMARY_CSV)
    with open(META_JSON, encoding="utf-8") as file:
        meta = json.load(file)

    candles = []
    for row in review.itertuples():
        candles.append({
            "time": row.date,
            "open": round(float(row.open), 4),
            "high": round(float(row.high), 4),
            "low": round(float(row.low), 4),
            "close": round(float(row.close), 4),
        })

    ema_values = calc_ema(review["close"].astype(float).tolist(), 20)
    ema = [
        {"time": review.iloc[index]["date"], "value": round(float(value), 4)}
        for index, value in enumerate(ema_values)
        if value is not None
    ]

    markers = {
        "sl7": [],
        "gt": [],
        "tp": [],
        "fp": [],
        "fn": [],
    }
    review_items = []
    for row in review.itertuples():
        if bool(row.is_sl_center):
            markers["sl7"].append({
                "time": row.date,
                "position": "belowBar",
                "shape": "square",
                "color": "#42A5F5",
                "text": "SL7",
            })
        if bool(row.is_gt):
            markers["gt"].append({
                "time": row.date,
                "position": "belowBar",
                "shape": "circle",
                "color": "#AB47BC",
                "text": "GT",
            })
        if row.outcome == "TP":
            markers["tp"].append({
                "time": row.date,
                "position": "belowBar",
                "shape": "arrowUp",
                "color": "#26A69A",
                "text": "TP",
            })
        elif row.outcome == "FP":
            markers["fp"].append({
                "time": row.date,
                "position": "belowBar",
                "shape": "arrowUp",
                "color": "#FF9800",
                "text": "FP",
            })
        elif row.outcome == "FN":
            markers["fn"].append({
                "time": row.date,
                "position": "aboveBar",
                "shape": "circle",
                "color": "#9E9E9E",
                "text": "FN",
            })

        if row.outcome == "TN":
            continue
        premium = (
            None
            if pd.isna(row.sl_price_premium)
            else round(float(row.sl_price_premium), 6)
        )
        quality = (
            None
            if pd.isna(row.price_quality)
            else round(float(row.price_quality), 6)
        )
        probability = (
            None
            if pd.isna(row.oos_probability)
            else round(float(row.oos_probability), 6)
        )
        percentile = (
            None
            if pd.isna(row.train_percentile)
            else round(float(row.train_percentile), 6)
        )
        center_date = "" if pd.isna(row.sl_center_date) else row.sl_center_date
        review_items.append({
            "date": row.date,
            "outcome": row.outcome,
            "systemGt": bool(row.is_gt),
            "isSlCenter": bool(row.is_sl_center),
            "slCenterDate": center_date,
            "premium": premium,
            "quality": quality,
            "slDistance": (
                None if pd.isna(row.sl_distance) else int(row.sl_distance)
            ),
            "stage1": bool(row.is_stage1),
            "probability": probability,
            "percentile": percentile,
            "foldId": int(row.fold_id),
            "predicted": bool(row.is_predicted),
            "open": round(float(row.open), 4),
            "high": round(float(row.high), 4),
            "low": round(float(row.low), 4),
            "close": round(float(row.close), 4),
        })

    metric_scopes = {}
    for period in ["final_test", "all_new_oos"]:
        row = summary[
            (summary["period"] == period)
            & (summary["variant"] == "spatial_p0080_l025_q50")
        ].iloc[0]
        metric_scopes[period] = {
            "label": "最终测试" if period == "final_test" else "全部 OOS",
            "start": row["start"],
            "end": row["end"],
            "precision": float(row["precision"]),
            "recall": float(row["recall"]),
            "f1": float(row["f1"]),
            "accuracy": float(row["accuracy"]),
            "tp": int(row["tp"]),
            "fp": int(row["fp"]),
            "fn": int(row["fn"]),
            "tn": int(row["tn"]),
            "gtDays": int(row["gt_days"]),
            "predictedDays": int(row["predicted_days"]),
            "eventPrecision": float(row["event_precision"]),
            "eventRecall": float(row["event_recall"]),
            "eventF1": float(row["event_f1"]),
        }

    return {
        "candles": candles,
        "ema": ema,
        "markers": markers,
        "reviewItems": review_items,
        "metricScopes": metric_scopes,
        "meta": meta,
    }


def _build_html(payload):
    title = "空间 GT 人工审核 · Walk-Forward OOS"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; min-height: 100%; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #131722; color: #d1d4dc;
  }}
  button, input, textarea {{ font: inherit; }}
  button {{
    min-height: 32px; padding: 5px 10px; border: 1px solid #434651;
    border-radius: 4px; background: #1e222d; color: #d1d4dc; cursor: pointer;
  }}
  button:hover {{ border-color: #8a8e9a; }}
  button:focus-visible, input:focus-visible, textarea:focus-visible {{
    outline: 2px solid #90caf9; outline-offset: 2px;
  }}
  button.active {{ background: #d1d4dc; color: #131722; border-color: #d1d4dc; }}
  button.accept.active {{ background: #26a69a; border-color: #26a69a; color: #fff; }}
  button.reject.active {{ background: #ef5350; border-color: #ef5350; color: #fff; }}
  button.unsure.active {{ background: #ff9800; border-color: #ff9800; color: #131722; }}
  #topbar {{
    display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
    padding: 10px 14px; background: #1e222d; border-bottom: 1px solid #2a2e39;
  }}
  h1 {{ margin: 0; font-size: 16px; font-weight: 500; }}
  .scope-group, .filter-group, .action-group {{
    display: flex; align-items: center; gap: 7px; flex-wrap: wrap;
  }}
  .metric {{ font-size: 13px; color: #9aa0aa; white-space: nowrap; }}
  .metric strong {{ color: #d1d4dc; font-weight: 500; }}
  .spacer {{ flex: 1 1 auto; }}
  #filters {{
    display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
    padding: 8px 14px; border-bottom: 1px solid #2a2e39;
  }}
  label.toggle {{ display: inline-flex; align-items: center; gap: 6px; font-size: 13px; }}
  .swatch {{ width: 11px; height: 11px; display: inline-block; }}
  .sl7 {{ background: #42a5f5; }}
  .gt {{ background: #ab47bc; border-radius: 50%; }}
  .tp {{ background: #26a69a; }}
  .fp {{ background: #ff9800; }}
  .fn {{ background: #9e9e9e; border-radius: 50%; }}
  #chart {{ width: 100%; height: 62vh; min-height: 420px; }}
  #review-band {{
    display: grid; grid-template-columns: minmax(0, 1fr) minmax(300px, 420px);
    gap: 18px; padding: 12px 14px 16px; border-top: 1px solid #2a2e39;
    background: #1e222d;
  }}
  #selected-summary {{ min-width: 0; }}
  #selected-title {{ margin: 0 0 8px; font-size: 15px; font-weight: 500; }}
  #facts {{
    display: grid; grid-template-columns: repeat(4, minmax(110px, 1fr));
    gap: 8px 14px; font-size: 13px;
  }}
  .fact-label {{ color: #787b86; display: block; margin-bottom: 2px; }}
  .fact-value {{ color: #d1d4dc; overflow-wrap: anywhere; }}
  #review-controls {{ min-width: 0; }}
  #review-progress {{ color: #9aa0aa; font-size: 13px; margin-bottom: 8px; }}
  #review-buttons {{ display: flex; gap: 7px; flex-wrap: wrap; margin-bottom: 8px; }}
  textarea {{
    width: 100%; min-height: 68px; resize: vertical; padding: 7px 8px;
    border: 1px solid #434651; border-radius: 4px;
    background: #131722; color: #d1d4dc;
  }}
  #review-nav {{
    display: flex; gap: 7px; align-items: center; flex-wrap: wrap; margin-top: 8px;
  }}
  #jump-date {{
    width: 130px; min-height: 32px; padding: 5px 7px;
    border: 1px solid #434651; border-radius: 4px;
    background: #131722; color: #d1d4dc;
  }}
  #empty-state {{ color: #787b86; font-size: 13px; }}
  .outcome-TP {{ color: #26a69a; }}
  .outcome-FP {{ color: #ff9800; }}
  .outcome-FN {{ color: #bdbdbd; }}
  @media (max-width: 820px) {{
    #chart {{ height: 54vh; min-height: 360px; }}
    #review-band {{ grid-template-columns: 1fr; }}
    #facts {{ grid-template-columns: repeat(2, minmax(110px, 1fr)); }}
  }}
  @media (max-width: 480px) {{
    #facts {{ grid-template-columns: 1fr; }}
    #chart {{ min-height: 320px; }}
  }}
</style>
</head>
<body>
<header id="topbar">
  <h1>{title}</h1>
  <div class="scope-group">
    <button id="scope-final_test" class="active" type="button">最终测试</button>
    <button id="scope-all_new_oos" type="button">全部 OOS</button>
  </div>
  <div class="metric">Precision <strong id="metric-p">-</strong></div>
  <div class="metric">Recall <strong id="metric-r">-</strong></div>
  <div class="metric">F1 <strong id="metric-f1">-</strong></div>
  <div class="metric">TP/FP/FN <strong id="metric-confusion">-</strong></div>
  <div class="spacer"></div>
  <div class="action-group">
    <button id="import-btn" type="button">导入审核</button>
    <input id="import-file" type="file" accept="application/json" hidden>
    <button id="export-btn" type="button">导出审核</button>
  </div>
</header>

<section id="filters" aria-label="图层过滤">
  <div class="filter-group">
    <label class="toggle"><input id="layer-sl7" type="checkbox" checked><span class="swatch sl7"></span>SL7 中心</label>
    <label class="toggle"><input id="layer-gt" type="checkbox"><span class="swatch gt"></span>全部 GT</label>
    <label class="toggle"><input id="layer-tp" type="checkbox" checked><span class="swatch tp"></span>TP 命中</label>
    <label class="toggle"><input id="layer-fp" type="checkbox" checked><span class="swatch fp"></span>FP 误报</label>
    <label class="toggle"><input id="layer-fn" type="checkbox" checked><span class="swatch fn"></span>FN 漏报</label>
  </div>
  <div class="spacer"></div>
  <label class="toggle"><input id="only-unreviewed" type="checkbox">导航只看未审核</label>
</section>

<main>
  <div id="chart" aria-label="SPY K 线及空间 GT 标记"></div>
</main>

<section id="review-band">
  <div id="selected-summary">
    <h2 id="selected-title">选择图上的 TP、FP 或 FN 标记开始审核</h2>
    <div id="facts"><div id="empty-state">点击标记，或使用“下一条”依次检查。</div></div>
  </div>
  <div id="review-controls">
    <div id="review-progress">已审核 0 / 0</div>
    <div id="review-buttons">
      <button id="decision-accept" class="accept" type="button">✓ 认可当前 GT</button>
      <button id="decision-reject" class="reject" type="button">× 不认可当前 GT</button>
      <button id="decision-unsure" class="unsure" type="button">? 不确定</button>
    </div>
    <textarea id="review-note" placeholder="审核备注"></textarea>
    <div id="review-nav">
      <button id="prev-btn" type="button">← 上一条</button>
      <button id="next-btn" type="button">下一条 →</button>
      <input id="jump-date" type="date" aria-label="跳转日期">
      <button id="jump-btn" type="button">跳转</button>
      <button id="clear-btn" type="button">清空审核</button>
    </div>
  </div>
</section>

<script src="lightweight-charts.standalone.production.js"></script>
<script>
const candleData = {_json(payload["candles"])};
const emaData = {_json(payload["ema"])};
const markerSets = {_json(payload["markers"])};
const reviewItems = {_json(payload["reviewItems"])};
const metricScopes = {_json(payload["metricScopes"])};
const runMeta = {_json(payload["meta"])};
const STORAGE_KEY = 'spatial-gt-human-review-v1';

const chart = LightweightCharts.createChart(document.getElementById('chart'), {{
  layout: {{ background: {{ color: '#131722' }}, textColor: '#d1d4dc' }},
  grid: {{
    vertLines: {{ color: '#1e222d' }},
    horzLines: {{ color: '#1e222d' }},
  }},
  crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
  timeScale: {{ borderColor: '#2a2e39', timeVisible: false }},
  rightPriceScale: {{ borderColor: '#2a2e39' }},
}});
const candleSeries = chart.addCandlestickSeries({{
  upColor: '#26a69a', downColor: '#ef5350',
  borderUpColor: '#26a69a', borderDownColor: '#ef5350',
  wickUpColor: '#26a69a', wickDownColor: '#ef5350',
}});
candleSeries.setData(candleData);
const emaSeries = chart.addLineSeries({{
  color: '#f9a825', lineWidth: 2, priceLineVisible: false,
  lastValueVisible: false, title: 'EMA20',
}});
emaSeries.setData(emaData);

const enabledLayers = {{
  sl7: document.getElementById('layer-sl7'),
  gt: document.getElementById('layer-gt'),
  tp: document.getElementById('layer-tp'),
  fp: document.getElementById('layer-fp'),
  fn: document.getElementById('layer-fn'),
}};
function renderMarkers() {{
  const visible = [];
  Object.entries(enabledLayers).forEach(([key, input]) => {{
    if (input.checked) visible.push(...(markerSets[key] || []));
  }});
  visible.sort((a, b) => a.time.localeCompare(b.time));
  candleSeries.setMarkers(visible);
}}
Object.values(enabledLayers).forEach(input => input.addEventListener('change', renderMarkers));
renderMarkers();

function dateKey(time) {{
  if (!time) return '';
  if (typeof time === 'string') return time;
  const month = String(time.month).padStart(2, '0');
  const day = String(time.day).padStart(2, '0');
  return `${{time.year}}-${{month}}-${{day}}`;
}}

const itemMap = new Map(reviewItems.map(item => [item.date, item]));
const candleIndex = new Map(candleData.map((item, index) => [item.time, index]));
let currentDate = '';
let currentScope = 'final_test';
let reviews = loadReviews();

function loadReviews() {{
  try {{
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{{}}');
  }} catch (error) {{
    return {{}};
  }}
}}
function persistReviews() {{
  localStorage.setItem(STORAGE_KEY, JSON.stringify(reviews));
  updateProgress();
}}
function formatPct(value) {{
  return value == null || Number.isNaN(value) ? '-' : `${{(value * 100).toFixed(2)}}%`;
}}
function formatNumber(value, digits = 3) {{
  return value == null || Number.isNaN(value) ? '-' : Number(value).toFixed(digits);
}}
function fact(label, value) {{
  return `<div><span class="fact-label">${{label}}</span><span class="fact-value">${{value}}</span></div>`;
}}

function applyScope(scope) {{
  currentScope = scope;
  Object.keys(metricScopes).forEach(key => {{
    document.getElementById(`scope-${{key}}`).classList.toggle('active', key === scope);
  }});
  const m = metricScopes[scope];
  document.getElementById('metric-p').textContent = formatPct(m.precision);
  document.getElementById('metric-r').textContent = formatPct(m.recall);
  document.getElementById('metric-f1').textContent = formatPct(m.f1);
  document.getElementById('metric-confusion').textContent = `${{m.tp}} / ${{m.fp}} / ${{m.fn}}`;
  updateProgress();
  const candidates = reviewCandidates();
  if (!currentDate || !candidates.some(item => item.date === currentDate)) {{
    if (candidates.length) selectItem(candidates[0].date);
  }}
}}
Object.keys(metricScopes).forEach(key => {{
  document.getElementById(`scope-${{key}}`).addEventListener('click', () => applyScope(key));
}});

function reviewCandidates() {{
  const onlyUnreviewed = document.getElementById('only-unreviewed').checked;
  const scope = metricScopes[currentScope];
  return reviewItems.filter(item => (
    item.date >= scope.start
    && item.date <= scope.end
    && (!onlyUnreviewed || !reviews[item.date])
  ));
}}
function updateProgress() {{
  const scope = metricScopes[currentScope];
  const scopedItems = reviewItems.filter(item => (
    item.date >= scope.start && item.date <= scope.end
  ));
  const reviewed = scopedItems.filter(item => reviews[item.date]).length;
  const reviewedAll = reviewItems.filter(item => reviews[item.date]).length;
  document.getElementById('review-progress').textContent =
    `本范围 ${{reviewed}} / ${{scopedItems.length}} · 全部 ${{reviewedAll}} / ${{reviewItems.length}}`;
}}
function updateDecisionButtons() {{
  const decision = (reviews[currentDate] || {{}}).decision || '';
  ['accept', 'reject', 'unsure'].forEach(value => {{
    document.getElementById(`decision-${{value}}`).classList.toggle('active', decision === value);
  }});
  document.getElementById('review-note').value = (reviews[currentDate] || {{}}).note || '';
}}
function focusDate(date) {{
  const index = candleIndex.get(date);
  if (index == null) return;
  const from = candleData[Math.max(0, index - 25)].time;
  const to = candleData[Math.min(candleData.length - 1, index + 25)].time;
  chart.timeScale().setVisibleRange({{ from, to }});
}}
function selectItem(date, shouldFocus = true) {{
  const item = itemMap.get(date);
  if (!item) return;
  currentDate = date;
  const gtText = item.systemGt ? 'GT 正例' : 'GT 负例';
  const prediction = item.predicted ? '模型放行' : '模型未放行';
  document.getElementById('selected-title').innerHTML =
    `<span class="outcome-${{item.outcome}}">${{item.outcome}}</span> · ${{item.date}} · ${{gtText}}`;
  document.getElementById('facts').innerHTML = [
    fact('收盘价', formatNumber(item.close, 2)),
    fact('SL7 中心', item.slCenterDate || '-'),
    fact('距离中心', item.slDistance == null ? '-' : `${{item.slDistance}} 根`),
    fact('离底溢价', formatPct(item.premium)),
    fact('价格质量', formatPct(item.quality)),
    fact('Stage 1', item.stage1 ? 'NDay2 候选' : '未进入候选'),
    fact('Stage 2', prediction),
    fact('OOS 概率', formatPct(item.probability)),
    fact('训练分位', formatPct(item.percentile)),
    fact('Walk-forward fold', item.foldId >= 0 ? String(item.foldId) : '-'),
    fact('系统 GT 判断', gtText),
    fact('SL7 中心日', item.isSlCenter ? '是' : '否'),
  ].join('');
  updateDecisionButtons();
  document.getElementById('jump-date').value = date;
  if (shouldFocus) focusDate(date);
}}

function moveSelection(direction) {{
  const candidates = reviewCandidates();
  if (!candidates.length) return;
  let index = candidates.findIndex(item => item.date === currentDate);
  if (index < 0) index = direction > 0 ? -1 : 0;
  const next = (index + direction + candidates.length) % candidates.length;
  selectItem(candidates[next].date);
}}

chart.subscribeClick(param => {{
  const key = dateKey(param.time);
  if (itemMap.has(key)) selectItem(key, false);
}});
document.getElementById('prev-btn').addEventListener('click', () => moveSelection(-1));
document.getElementById('next-btn').addEventListener('click', () => moveSelection(1));
document.getElementById('jump-btn').addEventListener('click', () => {{
  const date = document.getElementById('jump-date').value;
  if (itemMap.has(date)) selectItem(date);
  else if (candleIndex.has(date)) focusDate(date);
}});
document.getElementById('only-unreviewed').addEventListener('change', updateProgress);

function setDecision(decision) {{
  if (!currentDate) return;
  reviews[currentDate] = {{
    decision,
    note: document.getElementById('review-note').value.trim(),
    updatedAt: new Date().toISOString(),
  }};
  persistReviews();
  updateDecisionButtons();
}}
['accept', 'reject', 'unsure'].forEach(decision => {{
  document.getElementById(`decision-${{decision}}`).addEventListener('click', () => setDecision(decision));
}});
document.getElementById('review-note').addEventListener('change', () => {{
  if (!currentDate || !reviews[currentDate]) return;
  reviews[currentDate].note = document.getElementById('review-note').value.trim();
  reviews[currentDate].updatedAt = new Date().toISOString();
  persistReviews();
}});

document.getElementById('export-btn').addEventListener('click', () => {{
  const payload = {{
    schemaVersion: 1,
    exportedAt: new Date().toISOString(),
    model: 'spatial_p0080_l025_q50',
    runMeta,
    reviews: reviewItems
      .filter(item => reviews[item.date])
      .map(item => ({{ ...item, ...reviews[item.date] }})),
  }};
  const blob = new Blob([JSON.stringify(payload, null, 2)], {{ type: 'application/json' }});
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `spatial-gt-human-review-${{new Date().toISOString().slice(0, 10)}}.json`;
  document.body.appendChild(link);
  link.click();
  window.setTimeout(() => {{
    link.remove();
    URL.revokeObjectURL(url);
  }}, 0);
}});

const importFile = document.getElementById('import-file');
document.getElementById('import-btn').addEventListener('click', () => importFile.click());
importFile.addEventListener('change', async () => {{
  const file = importFile.files[0];
  if (!file) return;
  try {{
    const payload = JSON.parse(await file.text());
    const imported = {{}};
    (payload.reviews || []).forEach(item => {{
      imported[item.date] = {{
        decision: item.decision,
        note: item.note || '',
        updatedAt: item.updatedAt || new Date().toISOString(),
      }};
    }});
    reviews = {{ ...reviews, ...imported }};
    persistReviews();
    updateDecisionButtons();
  }} catch (error) {{
    window.alert('审核文件格式不正确');
  }}
  importFile.value = '';
}});
document.getElementById('clear-btn').addEventListener('click', () => {{
  if (!window.confirm('确认清空本浏览器中的全部审核记录？')) return;
  reviews = {{}};
  persistReviews();
  updateDecisionButtons();
}});

window.addEventListener('resize', () => {{
  chart.applyOptions({{
    width: document.getElementById('chart').clientWidth,
    height: document.getElementById('chart').clientHeight,
  }});
}});
chart.timeScale().setVisibleRange({{ from: '2020-01-01', to: '2026-04-02' }});
applyScope(currentScope);
</script>
</body>
</html>
"""


def build_review_chart(
    output_dir=OUTPUT_DIR,
    filename=DEFAULT_FILENAME,
    serve=False,
    port=9870,
):
    payload = _build_payload()
    html = _build_html(payload)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    _ensure_chart_lib(str(output_dir))
    path = output_dir / filename
    with open(path, "w", encoding="utf-8") as file:
        file.write(html)
    print(f"[输出] {path}")
    print(
        f"[审核] 可审核 {len(payload['reviewItems'])} 个 "
        "TP/FP/FN 日期，结果可导出 JSON"
    )
    if serve:
        _serve(str(output_dir), port, filename=filename)
    return path


def main():
    parser = argparse.ArgumentParser(description="生成空间 GT 人工审核 HTML")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument("--filename", default=DEFAULT_FILENAME)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=9870)
    args = parser.parse_args()
    build_review_chart(
        output_dir=args.output_dir,
        filename=args.filename,
        serve=args.serve,
        port=args.port,
    )


if __name__ == "__main__":
    main()
