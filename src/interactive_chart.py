"""
交互式 K 线图模块
生成自包含 HTML 并通过内置 HTTP 服务提供访问，在浏览器中提供类 TradingView 的交互式策略可视化
支持主图（K 线 + EMA + 交易标记）和 RSI 副图（RSI + 快均线 + 信号标记）
"""
import json
import os
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from functools import partial


# 固定文件名，每次覆盖，浏览器刷新即可看到最新结果
_HTML_FILENAME = 'interactive.html'


def show_interactive_chart(data, metrics, title='SOXL DCA 回测',
                           output_dir='output', port=9870, breadth_data=None,
                           vix_data=None, breadth_divergences=None,
                           breadth_consec=None, swing_lows=None,
                           show_trades=True):
    """
    生成交互式 K 线图并启动 HTTP 服务

    Args:
        data: K 线数据列表 [{'date', 'open', 'high', 'low', 'close'}, ...]
        metrics: BacktestEngine.run() 返回的结果字典
        title: 图表标题
        output_dir: HTML 文件保存目录
        port: HTTP 服务端口
        breadth_data: Market Breadth 数据列表 [{'time': 'YYYY-MM-DD', 'value': float}, ...]
    """
    # 构建 K 线数据
    candles = [
        {'time': d['date'], 'open': d['open'], 'high': d['high'],
         'low': d['low'], 'close': d['close']}
        for d in data
    ]

    # 构建 EMA 数据
    ema_series = metrics.get('ema_series', [])
    ema_data = []
    for i, day in enumerate(data):
        if ema_series and ema_series[i] is not None:
            ema_data.append({'time': day['date'], 'value': round(ema_series[i], 4)})

    # 构建交易标记
    markers = []
    trade_log = metrics.get('trade_log', [])
    if show_trades:
        for trade in trade_log:
            if trade['type'] == 'market_buy':
                markers.append({
                    'time': trade['date'],
                    'position': 'belowBar',
                    'shape': 'arrowUp',
                    'color': '#2196F3',
                    'text': f"买 {trade['shares']:.2f}股",
                })
            elif trade['type'] == 'limit_buy':
                pct = round((1 - trade['tier']) * 100)
                markers.append({
                    'time': trade['date'],
                    'position': 'belowBar',
                    'shape': 'arrowUp',
                    'color': '#4CAF50',
                    'text': f"限买 跌{pct}%",
                })
            elif trade['type'] == 'tp_sell':
                markers.append({
                    'time': trade['date'],
                    'position': 'aboveBar',
                    'shape': 'arrowDown',
                    'color': '#F44336',
                    'text': f"止盈 ${trade['profit']:.0f}",
                })

    # 按时间排序（Lightweight Charts 要求）
    markers.sort(key=lambda m: m['time'])

    # 构建 RSI 副图数据
    rsi_v2 = metrics.get('rsi_v2', {})
    rsi_data = []
    fast_ma_data = []
    rsi_markers = []

    if rsi_v2:
        rsi_series = rsi_v2.get('rsi', [])
        fast_ma_series = rsi_v2.get('fast_ma', [])
        signals_series = rsi_v2.get('signals', [])

        for i, day in enumerate(data):
            if i < len(rsi_series) and rsi_series[i] is not None:
                rsi_data.append({'time': day['date'], 'value': round(rsi_series[i], 2)})
            if i < len(fast_ma_series) and fast_ma_series[i] is not None:
                fast_ma_data.append({'time': day['date'], 'value': round(fast_ma_series[i], 2)})

            if i < len(signals_series) and signals_series[i]:
                # 取该 bar 上最高级别的买入和卖出信号各一个
                buy_sig = _best_signal(signals_series[i], 'B')
                sell_sig = _best_signal(signals_series[i], 'S')

                if buy_sig:
                    rsi_markers.append({
                        'time': day['date'],
                        'position': 'belowBar',
                        'shape': 'arrowUp',
                        'color': '#26a69a',
                        'text': buy_sig['type'],
                    })
                if sell_sig:
                    rsi_markers.append({
                        'time': day['date'],
                        'position': 'aboveBar',
                        'shape': 'arrowDown',
                        'color': '#ef5350',
                        'text': sell_sig['type'],
                    })

        rsi_markers.sort(key=lambda m: m['time'])

    # 摘要信息
    summary = {
        'total_return': f"{metrics['total_return']*100:+.2f}%",
        'sharpe': f"{metrics['sharpe_ratio']:.2f}",
        'max_drawdown': f"{metrics['max_drawdown']*100:.1f}%",
        'trade_count': len(trade_log),
    }

    html = _build_html(title, candles, ema_data, markers, summary,
                       rsi_data, fast_ma_data, rsi_markers,
                       breadth_data=breadth_data, vix_data=vix_data,
                       breadth_divergences=breadth_divergences,
                       breadth_consec=breadth_consec,
                       swing_lows=swing_lows)

    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, _HTML_FILENAME)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)

    _serve(output_dir, port)


def _best_signal(signals, prefix):
    """从同一 bar 的多个信号中选最高级别的（B++ > B+ > B）"""
    rank = {f'{prefix}++': 3, f'{prefix}+': 2, prefix: 1}
    best = None
    best_rank = 0
    for sig in signals:
        r = rank.get(sig['type'], 0)
        if r > best_rank:
            best = sig
            best_rank = r
    return best


def _serve(directory, port):
    """启动 HTTP 服务，供本地浏览器访问"""
    abs_dir = os.path.abspath(directory)
    handler = partial(SimpleHTTPRequestHandler, directory=abs_dir)

    # 抑制请求日志
    handler.log_message = lambda *args, **kwargs: None

    try:
        server = HTTPServer(('0.0.0.0', port), handler)
    except OSError as e:
        if 'Address already in use' in str(e):
            print(f'\n图表已更新，刷新浏览器即可查看最新结果')
            print(f'  → http://<服务器IP>:{port}/{_HTML_FILENAME}')
            return
        raise

    hostname = _get_hostname()
    url = f'http://{hostname}:{port}/{_HTML_FILENAME}'
    print(f'\n图表服务已启动：')
    print(f'  → {url}')
    print(f'\n在本地浏览器打开上面的地址即可查看')
    print(f'重新运行回测后，刷新浏览器即可看到新结果')
    print(f'按 Ctrl+C 停止服务')

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n图表服务已停止')
        server.server_close()


def _get_hostname():
    """获取服务器可访问的 IP 或主机名"""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return socket.gethostname()


def _build_html(title, candles, ema_data, markers, summary,
                rsi_data=None, fast_ma_data=None, rsi_markers=None,
                breadth_data=None, vix_data=None, breadth_divergences=None,
                breadth_consec=None, swing_lows=None):
    """生成自包含的 HTML 文件内容"""

    has_rsi = bool(rsi_data and len(rsi_data) > 0)
    has_breadth = bool(breadth_data and len(breadth_data) > 0)
    has_vix = bool(vix_data and len(vix_data) > 0)

    # 高度分配：根据面板数量动态调整
    sub_count = sum([has_rsi, has_breadth, has_vix])
    if sub_count >= 3:
        main_height = 'calc(40vh - 48px)'
        rsi_height = 'calc(20vh)' if has_rsi else '0'
        breadth_height = 'calc(20vh)' if has_breadth else '0'
        vix_height = 'calc(20vh)' if has_vix else '0'
    elif sub_count == 2:
        main_height = 'calc(50vh - 48px)'
        rsi_height = 'calc(25vh)' if has_rsi else '0'
        breadth_height = 'calc(25vh)' if has_breadth else '0'
        vix_height = 'calc(25vh)' if has_vix else '0'
    elif sub_count == 1:
        main_height = 'calc(70vh - 48px)'
        rsi_height = 'calc(30vh)' if has_rsi else '0'
        breadth_height = 'calc(30vh)' if has_breadth else '0'
        vix_height = 'calc(30vh)' if has_vix else '0'
    else:
        main_height = 'calc(100vh - 48px)'
        rsi_height = '0'
        breadth_height = '0'
        vix_height = '0'

    # 副图的 HTML
    rsi_div_html = '<div id="rsi-chart"></div>' if has_rsi else ''
    breadth_div_html = '<div id="breadth-chart"></div>' if has_breadth else ''
    vix_div_html = '<div id="vix-chart"></div>' if has_vix else ''

    rsi_js = ''
    if has_rsi:
        rsi_js = f'''
// ═══════════════════════════════════════════════════
//  RSI 副图
// ═══════════════════════════════════════════════════

const rsiChart = LightweightCharts.createChart(document.getElementById('rsi-chart'), {{
  layout: {{ background: {{ color: initTheme.bg }}, textColor: initTheme.text }},
  grid: {{
    vertLines: {{ color: initTheme.grid }},
    horzLines: {{ color: initTheme.grid }},
  }},
  crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
  timeScale: {{ timeVisible: false, borderColor: initTheme.border }},
  rightPriceScale: {{ borderColor: initTheme.border, scaleMargins: {{ top: 0.05, bottom: 0.05 }} }},
}});

// RSI 曲线（紫色）
const rsiSeries = rsiChart.addLineSeries({{
  color: '#7E57C2', lineWidth: 1, priceLineVisible: false, lastValueVisible: true,
  title: 'RSI',
}});
rsiSeries.setData({json.dumps(rsi_data)});

// 70/30 水平参考线
rsiSeries.createPriceLine({{ price: 70, color: '#787B86', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: '' }});
rsiSeries.createPriceLine({{ price: 30, color: '#787B86', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: '' }});
rsiSeries.createPriceLine({{ price: 50, color: 'rgba(120,123,134,0.3)', lineWidth: 1, lineStyle: 1, axisLabelVisible: false, title: '' }});

// 快均线（橙黄色加粗）
const fastMaData = {json.dumps(fast_ma_data if fast_ma_data else [])};
if (fastMaData.length > 0) {{
  const fastMaSeries = rsiChart.addLineSeries({{
    color: '#FF9800', lineWidth: 2, priceLineVisible: false, lastValueVisible: false,
    title: 'EMA5',
  }});
  fastMaSeries.setData(fastMaData);
}}

// RSI 信号标记
const rsiMarkers = {json.dumps(rsi_markers if rsi_markers else [], ensure_ascii=False)};
if (rsiMarkers.length > 0) {{
  rsiSeries.setMarkers(rsiMarkers);
}}

// 多图同步（时间轴 + 十字光标），支持 2~3 个图表
const allCharts = [{{ chart: chart, series: candleSeries }}];
allCharts.push({{ chart: rsiChart, series: rsiSeries }});

let isSyncing = false;
function syncTimeRange(source, range) {{
  if (!range || isSyncing) return;
  isSyncing = true;
  allCharts.forEach(c => {{
    if (c.chart !== source) c.chart.timeScale().setVisibleRange(range);
  }});
  isSyncing = false;
}}
function syncCrosshair(source, param) {{
  if (!param.time) return;
  allCharts.forEach(c => {{
    if (c.chart !== source) c.chart.setCrosshairPosition(undefined, param.time, c.series);
  }});
}}
allCharts.forEach(c => {{
  c.chart.timeScale().subscribeVisibleTimeRangeChange(r => syncTimeRange(c.chart, r));
  c.chart.subscribeCrosshairMove(p => syncCrosshair(c.chart, p));
}});

rsiChart.timeScale().fitContent();

// 窗口缩放时同步调整 RSI 图
window.addEventListener('resize', () => {{
  rsiChart.applyOptions({{
    width: document.getElementById('rsi-chart').clientWidth,
    height: document.getElementById('rsi-chart').clientHeight,
  }});
}});
'''

    breadth_js = ''
    if has_breadth:
        breadth_js = f'''
// ═══════════════════════════════════════════════════
//  Market Breadth 副图
// ═══════════════════════════════════════════════════

const breadthChart = LightweightCharts.createChart(document.getElementById('breadth-chart'), {{
  layout: {{ background: {{ color: initTheme.bg }}, textColor: initTheme.text }},
  grid: {{
    vertLines: {{ color: initTheme.grid }},
    horzLines: {{ color: initTheme.grid }},
  }},
  crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
  timeScale: {{ timeVisible: false, borderColor: initTheme.border }},
  rightPriceScale: {{ borderColor: initTheme.border, scaleMargins: {{ top: 0.05, bottom: 0.05 }} }},
}});

// Breadth 曲线
const breadthSeries = breadthChart.addLineSeries({{
  color: '#2196F3', lineWidth: 2, priceLineVisible: false, lastValueVisible: true,
  title: 'Breadth',
}});
const breadthData = {json.dumps(breadth_data)};
breadthSeries.setData(breadthData);

// ── 连续弱势曲线 c2~c5 ──
const breadthConsec = {json.dumps(breadth_consec if breadth_consec else {{}})};
const consecColors = {{
  c2: '#66BB6A',  // 绿色
  c3: '#FFA726',  // 橙色
  c4: '#EF5350',  // 红色
  c5: '#AB47BC',  // 紫色
}};
const consecLabels = {{
  c2: 'C2 (≥2天)',
  c3: 'C3 (≥3天)',
  c4: 'C4 (≥4天)',
  c5: 'C5 (≥5天)',
}};
['c2', 'c3', 'c4', 'c5'].forEach(key => {{
  if (breadthConsec[key] && breadthConsec[key].length > 0) {{
    const s = breadthChart.addLineSeries({{
      color: consecColors[key],
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
      title: consecLabels[key],
    }});
    s.setData(breadthConsec[key]);
  }}
}});

// 填充区域：用 Baseline Series 实现 Breadth 曲线本身的上下填色
// 当 Breadth > 80 时显示绿色填充，< 20 时显示红色填充
const breadthFill = breadthChart.addBaselineSeries({{
  baseValue: {{ type: 'price', price: 50 }},
  topLineColor: 'transparent',
  topFillColor1: 'rgba(38, 166, 154, 0.15)',
  topFillColor2: 'transparent',
  bottomLineColor: 'transparent',
  bottomFillColor1: 'transparent',
  bottomFillColor2: 'rgba(239, 83, 80, 0.15)',
  lineWidth: 0,
  priceLineVisible: false,
  lastValueVisible: false,
  crosshairMarkerVisible: false,
}});
breadthFill.setData(breadthData);

// 参考线：20（红）、50（灰）、80（绿）
breadthSeries.createPriceLine({{ price: 80, color: '#26a69a', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: '' }});
breadthSeries.createPriceLine({{ price: 50, color: '#787B86', lineWidth: 1, lineStyle: 1, axisLabelVisible: false, title: '' }});
breadthSeries.createPriceLine({{ price: 20, color: '#ef5350', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: '' }});

// ── Breadth 背离标记 + 连线 ──
const breadthDivergences = {json.dumps(breadth_divergences if breadth_divergences else [])};
if (breadthDivergences.length > 0) {{
  // 背离标记（在触发点 B 处画向上箭头）
  const divMarkers = breadthDivergences.map(d => ({{
    time: d.date_b,
    position: 'belowBar',
    shape: 'arrowUp',
    color: '#FF6D00',
    text: 'Div',
  }}));
  divMarkers.sort((a, b) => a.time < b.time ? -1 : 1);
  breadthSeries.setMarkers(divMarkers);

  // 背离连线（A→B 两点之间画线，每条背离一条独立线段）
  breadthDivergences.forEach(d => {{
    const lineSeries = breadthChart.addLineSeries({{
      color: '#FF6D00',
      lineWidth: 2,
      lineStyle: 2,  // 虚线
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    }});
    lineSeries.setData([
      {{ time: d.date_a, value: d.breadth_a }},
      {{ time: d.date_b, value: d.breadth_b }},
    ]);
  }});
}}

// 将 Breadth 图加入同步数组（如果存在）
if (typeof allCharts !== 'undefined') {{
  allCharts.push({{ chart: breadthChart, series: breadthSeries }});
  breadthChart.timeScale().subscribeVisibleTimeRangeChange(r => syncTimeRange(breadthChart, r));
  breadthChart.subscribeCrosshairMove(p => syncCrosshair(breadthChart, p));
}} else {{
  // 没有 RSI 图时，直接与主图同步
  let isSyncing = false;
  chart.timeScale().subscribeVisibleTimeRangeChange(range => {{
    if (range && !isSyncing) {{
      isSyncing = true;
      breadthChart.timeScale().setVisibleRange(range);
      isSyncing = false;
    }}
  }});
  breadthChart.timeScale().subscribeVisibleTimeRangeChange(range => {{
    if (range && !isSyncing) {{
      isSyncing = true;
      chart.timeScale().setVisibleRange(range);
      isSyncing = false;
    }}
  }});
  chart.subscribeCrosshairMove(param => {{
    if (param.time) breadthChart.setCrosshairPosition(undefined, param.time, breadthSeries);
  }});
  breadthChart.subscribeCrosshairMove(param => {{
    if (param.time) chart.setCrosshairPosition(undefined, param.time, candleSeries);
  }});
}}

breadthChart.timeScale().fitContent();

// 窗口缩放时调整 Breadth 图
window.addEventListener('resize', () => {{
  breadthChart.applyOptions({{
    width: document.getElementById('breadth-chart').clientWidth,
    height: document.getElementById('breadth-chart').clientHeight,
  }});
}});
'''

    vix_js = ''
    if has_vix:
        vix_js = f'''
// ═══════════════════════════════════════════════════
//  VIX 副图
// ═══════════════════════════════════════════════════

const vixChart = LightweightCharts.createChart(document.getElementById('vix-chart'), {{
  layout: {{ background: {{ color: initTheme.bg }}, textColor: initTheme.text }},
  grid: {{
    vertLines: {{ color: initTheme.grid }},
    horzLines: {{ color: initTheme.grid }},
  }},
  crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
  timeScale: {{ timeVisible: false, borderColor: initTheme.border }},
  rightPriceScale: {{ borderColor: initTheme.border, scaleMargins: {{ top: 0.05, bottom: 0.05 }} }},
}});

// VIX 曲线（蓝色）
const vixSeries = vixChart.addLineSeries({{
  color: '#2196F3', lineWidth: 2, priceLineVisible: false, lastValueVisible: true,
  title: 'VIX',
}});
const vixData = {json.dumps(vix_data)};
vixSeries.setData(vixData);

// 恐慌区域填充（> 30 红色半透明）
const vixFill = vixChart.addBaselineSeries({{
  baseValue: {{ type: 'price', price: 30 }},
  topLineColor: 'transparent',
  topFillColor1: 'rgba(239, 83, 80, 0.25)',
  topFillColor2: 'rgba(239, 83, 80, 0.05)',
  bottomLineColor: 'transparent',
  bottomFillColor1: 'transparent',
  bottomFillColor2: 'transparent',
  lineWidth: 0,
  priceLineVisible: false,
  lastValueVisible: false,
  crosshairMarkerVisible: false,
}});
vixFill.setData(vixData);

// 参考线：20（黄色虚线）、30（红色虚线）
vixSeries.createPriceLine({{ price: 20, color: '#FF9800', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: '' }});
vixSeries.createPriceLine({{ price: 30, color: '#ef5350', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: '' }});

// 将 VIX 图加入同步数组（如果存在）
if (typeof allCharts !== 'undefined') {{
  allCharts.push({{ chart: vixChart, series: vixSeries }});
  vixChart.timeScale().subscribeVisibleTimeRangeChange(r => syncTimeRange(vixChart, r));
  vixChart.subscribeCrosshairMove(p => syncCrosshair(vixChart, p));
}} else {{
  // 没有 RSI/Breadth 图时，直接与主图同步
  let isSyncing = false;
  chart.timeScale().subscribeVisibleTimeRangeChange(range => {{
    if (range && !isSyncing) {{
      isSyncing = true;
      vixChart.timeScale().setVisibleRange(range);
      isSyncing = false;
    }}
  }});
  vixChart.timeScale().subscribeVisibleTimeRangeChange(range => {{
    if (range && !isSyncing) {{
      isSyncing = true;
      chart.timeScale().setVisibleRange(range);
      isSyncing = false;
    }}
  }});
  chart.subscribeCrosshairMove(param => {{
    if (param.time) vixChart.setCrosshairPosition(undefined, param.time, vixSeries);
  }});
  vixChart.subscribeCrosshairMove(param => {{
    if (param.time) chart.setCrosshairPosition(undefined, param.time, candleSeries);
  }});
}}

vixChart.timeScale().fitContent();

// 窗口缩放时调整 VIX 图
window.addEventListener('resize', () => {{
  vixChart.applyOptions({{
    width: document.getElementById('vix-chart').clientWidth,
    height: document.getElementById('vix-chart').clientHeight,
  }});
}});
'''

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; transition: background 0.3s, color 0.3s; }}
  body.dark {{ background: #131722; color: #d1d4dc; }}
  body.light {{ background: #ffffff; color: #333333; }}
  #header {{
    padding: 12px 20px; display: flex; align-items: center; gap: 24px;
    transition: background 0.3s, border-color 0.3s;
  }}
  body.dark #header {{ background: #1e222d; border-bottom: 1px solid #2a2e39; }}
  body.light #header {{ background: #f0f3fa; border-bottom: 1px solid #d6dcde; }}
  #header h1 {{ font-size: 16px; font-weight: 600; }}
  .stat {{ font-size: 13px; }}
  body.dark .stat {{ color: #787b86; }}
  body.light .stat {{ color: #888; }}
  body.dark .stat span {{ color: #d1d4dc; font-weight: 500; }}
  body.light .stat span {{ color: #333; font-weight: 500; }}
  #theme-toggle {{
    margin-left: auto; cursor: pointer; font-size: 18px;
    background: none; border: 1px solid #555; border-radius: 6px;
    padding: 4px 10px; transition: all 0.3s;
  }}
  body.dark #theme-toggle {{ color: #d1d4dc; border-color: #555; }}
  body.light #theme-toggle {{ color: #333; border-color: #ccc; }}
  #theme-toggle:hover {{ opacity: 0.7; }}
  #chart {{ width: 100%; height: {main_height}; }}
  #rsi-chart {{ width: 100%; height: {rsi_height}; }}
  body.dark #rsi-chart {{ border-top: 1px solid #2a2e39; }}
  body.light #rsi-chart {{ border-top: 1px solid #d6dcde; }}
  #breadth-chart {{ width: 100%; height: {breadth_height}; }}
  body.dark #breadth-chart {{ border-top: 1px solid #2a2e39; }}
  body.light #breadth-chart {{ border-top: 1px solid #d6dcde; }}
  #vix-chart {{ width: 100%; height: {vix_height}; }}
  body.dark #vix-chart {{ border-top: 1px solid #2a2e39; }}
  body.light #vix-chart {{ border-top: 1px solid #d6dcde; }}
</style>
</head>
<body class="dark">
<div id="header">
  <h1>{title}</h1>
  <div class="stat">收益率 <span>{summary['total_return']}</span></div>
  <div class="stat">夏普 <span>{summary['sharpe']}</span></div>
  <div class="stat">最大回撤 <span>{summary['max_drawdown']}</span></div>
  <div class="stat">交易 <span>{summary['trade_count']} 笔</span></div>
  <button id="theme-toggle" onclick="toggleTheme()">&#9788;</button>
</div>
<div id="chart"></div>
{rsi_div_html}
{breadth_div_html}
{vix_div_html}

<script src="https://unpkg.com/lightweight-charts@4.1.0/dist/lightweight-charts.standalone.production.js"></script>
<script>
// ═══════════════════════════════════════════════════
//  主题配置
// ═══════════════════════════════════════════════════
const themes = {{
  dark: {{
    bg: '#131722', text: '#d1d4dc',
    grid: '#1e222d', border: '#2a2e39',
  }},
  light: {{
    bg: '#ffffff', text: '#333333',
    grid: '#f0f0f0', border: '#d6dcde',
  }},
}};
let currentTheme = localStorage.getItem('chartTheme') || 'dark';

function applyTheme(theme) {{
  const t = themes[theme];
  document.body.className = theme;
  const btn = document.getElementById('theme-toggle');
  btn.textContent = theme === 'dark' ? '\u2606' : '\u2605';

  const chartOpts = {{
    layout: {{ background: {{ color: t.bg }}, textColor: t.text }},
    grid: {{ vertLines: {{ color: t.grid }}, horzLines: {{ color: t.grid }} }},
    timeScale: {{ borderColor: t.border }},
    rightPriceScale: {{ borderColor: t.border }},
  }};
  chart.applyOptions(chartOpts);
  if (typeof rsiChart !== 'undefined') rsiChart.applyOptions(chartOpts);
  if (typeof breadthChart !== 'undefined') breadthChart.applyOptions(chartOpts);
  if (typeof vixChart !== 'undefined') vixChart.applyOptions(chartOpts);
  localStorage.setItem('chartTheme', theme);
}}

function toggleTheme() {{
  currentTheme = currentTheme === 'dark' ? 'light' : 'dark';
  applyTheme(currentTheme);
}}

// ═══════════════════════════════════════════════════
//  主图
// ═══════════════════════════════════════════════════
const initTheme = themes[currentTheme];
const chart = LightweightCharts.createChart(document.getElementById('chart'), {{
  layout: {{ background: {{ color: initTheme.bg }}, textColor: initTheme.text }},
  grid: {{
    vertLines: {{ color: initTheme.grid }},
    horzLines: {{ color: initTheme.grid }},
  }},
  crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
  timeScale: {{ timeVisible: false, borderColor: initTheme.border }},
  rightPriceScale: {{ borderColor: initTheme.border }},
}});

// K 线
const candleSeries = chart.addCandlestickSeries({{
  upColor: '#26a69a', downColor: '#ef5350',
  borderUpColor: '#26a69a', borderDownColor: '#ef5350',
  wickUpColor: '#26a69a', wickDownColor: '#ef5350',
}});
const candleData = {json.dumps(candles)};
candleSeries.setData(candleData);

// EMA 线
const emaData = {json.dumps(ema_data)};
if (emaData.length > 0) {{
  const emaSeries = chart.addLineSeries({{
    color: '#FF9800', lineWidth: 2, priceLineVisible: false,
    lastValueVisible: false,
  }});
  emaSeries.setData(emaData);
}}

// 交易标记 + Swing Low 标记（合并到同一个 markers 数组）
const markers = {json.dumps(markers, ensure_ascii=False)};
const swingLows = {json.dumps(swing_lows if swing_lows else {{}})};
// Swing Low 标记：保留=橙色，被过滤=灰色
const swingConfig = {{
  '10': {{ color: '#FF6D00', text: 'SL10' }},
  'filtered': {{ color: '#888888', text: 'x' }},
}};
Object.keys(swingLows).forEach(key => {{
  const cfg = swingConfig[key] || {{ color: '#888', text: 'SL' }};
  (swingLows[key] || []).forEach(pt => {{
    markers.push({{
      time: pt.date,
      position: 'belowBar',
      shape: 'circle',
      color: cfg.color,
      text: cfg.text,
    }});
  }});
}});
markers.sort((a, b) => a.time < b.time ? -1 : a.time > b.time ? 1 : 0);
if (markers.length > 0) {{
  candleSeries.setMarkers(markers);
}}

// 自适应窗口大小
chart.timeScale().fitContent();
window.addEventListener('resize', () => {{
  chart.applyOptions({{
    width: document.getElementById('chart').clientWidth,
    height: document.getElementById('chart').clientHeight,
  }});
}});

{rsi_js}

{breadth_js}

{vix_js}

// 应用保存的主题偏好
if (currentTheme === 'light') applyTheme('light');
</script>
</body>
</html>'''
