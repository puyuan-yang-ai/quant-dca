"""
ML 信号可视化 — Lightweight Charts 交互式图表

在 SPY 价格走势上标注 ML 信号点（绿色=赚钱, 红色=亏钱）。

使用方式:
    cd /home/puyuyang/Projects/quant-dca
    .venv/bin/python -m ml.show_signals_chart [--port 9871]
"""
import os
import sys
import json
import argparse
import importlib
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ml.labeling import (
    load_spy,
    generate_nday_signals,
    create_labels,
    create_labels_sl_proximity,
    create_labels_sl_multi,
)
from ml.versions import ACTIVE_VERSION, get_active_config
from xgboost import XGBClassifier
import numpy as np

OUTPUT_DIR = Path(__file__).parent.parent / "output"


def generate_ml_signals():
    """训练模型并返回测试集信号"""
    config = get_active_config()
    lab_cfg = config["labeling"]
    feat_mod = importlib.import_module(config["features_module"])

    spy_df = load_spy()
    signal = generate_nday_signals(spy_df, n=5)
    lab_method = lab_cfg.get("method", "fixed_horizon")
    if lab_method == "sl_proximity":
        labeled = create_labels_sl_proximity(
            spy_df,
            signal,
            sl_n=lab_cfg.get("sl_n", 7),
            k=lab_cfg.get("k", 3),
        )
    elif lab_method == "sl_multi":
        labeled = create_labels_sl_multi(
            spy_df,
            signal,
            sl_ns=lab_cfg.get("sl_ns", [5, 7]),
            k=lab_cfg.get("k", 3),
        )
    else:
        labeled = create_labels(spy_df, signal, horizon=lab_cfg.get("horizon", 5))

    print(f"[Version] 使用激活版本: {ACTIVE_VERSION}")
    print("[1/3] 构造特征...")
    data, feature_cols = feat_mod.build_features(labeled, spy_df)
    data = data.dropna(subset=feature_cols)

    split_idx = int(len(data) * 0.8)
    train = data.iloc[:split_idx]
    test = data.iloc[split_idx:]

    print("[2/3] 训练模型...")
    X_train = train[feature_cols].values
    y_train = train["label"].values
    X_test = test[feature_cols].values

    model = XGBClassifier(
        n_estimators=100, max_depth=4, learning_rate=0.1,
        eval_metric="logloss", random_state=42, verbosity=0,
    )
    model.fit(X_train, y_train)
    proba = model.predict_proba(X_test)[:, 1]

    test = test.copy()
    test["proba"] = proba
    test["ml_pass"] = proba >= 0.5

    print(f"[3/3] 测试期: {test['date'].iloc[0].strftime('%Y-%m-%d')} ~ {test['date'].iloc[-1].strftime('%Y-%m-%d')}")
    print(f"       ML通过信号: {test['ml_pass'].sum()} / {len(test)}")

    return spy_df, test


def build_chart_html(spy_df, test_signals):
    """生成 Lightweight Charts HTML"""
    test_start = test_signals["date"].iloc[0]
    test_end = test_signals["date"].iloc[-1]

    chart_data = spy_df[
        (spy_df["date"] >= test_start - np.timedelta64(60, "D")) &
        (spy_df["date"] <= test_end)
    ].copy()

    candles = [
        {"time": row["date"].strftime("%Y-%m-%d"),
         "open": round(row["open"], 2), "high": round(row["high"], 2),
         "low": round(row["low"], 2), "close": round(row["close"], 2)}
        for _, row in chart_data.iterrows()
    ]

    ema20 = chart_data["close"].ewm(span=20, adjust=False).mean()
    ema_data = [
        {"time": row["date"].strftime("%Y-%m-%d"), "value": round(ema20.iloc[i], 2)}
        for i, (_, row) in enumerate(chart_data.iterrows())
        if not np.isnan(ema20.iloc[i])
    ]

    markers = []
    for _, sig in test_signals.iterrows():
        if not sig["ml_pass"]:
            continue
        is_win = sig["forward_return"] > 0
        markers.append({
            "time": sig["date"].strftime("%Y-%m-%d"),
            "position": "belowBar",
            "shape": "arrowUp",
            "color": "#4CAF50" if is_win else "#F44336",
            "text": f"{'WIN' if is_win else 'LOSS'} {sig['forward_return']*100:.1f}% (p={sig['proba']:.2f})",
        })

    rejected = test_signals[~test_signals["ml_pass"]]
    for _, sig in rejected.iterrows():
        is_win = sig["forward_return"] > 0
        markers.append({
            "time": sig["date"].strftime("%Y-%m-%d"),
            "position": "aboveBar",
            "shape": "circle",
            "color": "#9E9E9E",
            "text": f"SKIP (p={sig['proba']:.2f})",
        })

    markers.sort(key=lambda m: m["time"])

    win_count = test_signals[test_signals["ml_pass"] & (test_signals["forward_return"] > 0)].shape[0]
    total_pass = test_signals["ml_pass"].sum()
    win_rate = win_count / total_pass * 100 if total_pass > 0 else 0

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>ML Signal Visualization</title>
    <script src="https://unpkg.com/lightweight-charts@4.1.0/dist/lightweight-charts.standalone.production.js"></script>
    <style>
        body {{ margin: 0; padding: 0; background: #1e1e1e; font-family: monospace; }}
        #header {{ color: #ccc; padding: 10px 20px; font-size: 14px; }}
        #header span {{ margin-right: 20px; }}
        .win {{ color: #4CAF50; }}
        .loss {{ color: #F44336; }}
        .skip {{ color: #9E9E9E; }}
        #chart {{ width: 100%; height: calc(100vh - 60px); }}
    </style>
</head>
<body>
    <div id="header">
        <span>ML Meta-Labeling Signal Chart | Test: {test_signals['date'].iloc[0].strftime('%Y-%m-%d')} ~ {test_signals['date'].iloc[-1].strftime('%Y-%m-%d')}</span>
        <span class="win">▲ WIN ({win_count})</span>
        <span class="loss">▲ LOSS ({total_pass - win_count})</span>
        <span class="skip">● SKIP ({len(rejected)})</span>
        <span>| WinRate: {win_rate:.1f}% | Pass: {total_pass}/{len(test_signals)}</span>
    </div>
    <div id="chart"></div>
    <script>
        const chart = LightweightCharts.createChart(document.getElementById('chart'), {{
            layout: {{ background: {{ color: '#1e1e1e' }}, textColor: '#ccc' }},
            grid: {{ vertLines: {{ color: '#2d2d2d' }}, horzLines: {{ color: '#2d2d2d' }} }},
            crosshair: {{ mode: 0 }},
            timeScale: {{ timeVisible: false }},
        }});

        const candleSeries = chart.addCandlestickSeries({{
            upColor: '#26a69a', downColor: '#ef5350',
            borderUpColor: '#26a69a', borderDownColor: '#ef5350',
            wickUpColor: '#26a69a', wickDownColor: '#ef5350',
        }});
        candleSeries.setData({json.dumps(candles)});

        const emaSeries = chart.addLineSeries({{
            color: '#FFD700', lineWidth: 1, title: 'EMA20',
        }});
        emaSeries.setData({json.dumps(ema_data)});

        candleSeries.setMarkers({json.dumps(markers)});

        chart.timeScale().fitContent();
    </script>
</body>
</html>"""

    return html


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9871)
    args = parser.parse_args()

    print("=" * 50)
    print("  ML Signal Visualization")
    print("=" * 50)

    spy_df, test_signals = generate_ml_signals()
    html = build_chart_html(spy_df, test_signals)

    OUTPUT_DIR.mkdir(exist_ok=True)
    html_path = OUTPUT_DIR / "ml_signals.html"
    with open(html_path, "w") as f:
        f.write(html)

    print(f"\n[Output] HTML 已保存: {html_path}")
    print(f"[Server] 启动 HTTP 服务 http://localhost:{args.port}")
    print(f"         Ctrl+C 退出\n")

    handler = partial(SimpleHTTPRequestHandler, directory=str(OUTPUT_DIR))
    server = HTTPServer(("0.0.0.0", args.port), handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
        server.shutdown()


if __name__ == "__main__":
    main()
