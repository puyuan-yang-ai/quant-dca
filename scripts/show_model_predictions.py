"""
把模型的【测试集(Walk-Forward OOS)买点预测】画到主交互图上（9870 风格）。

- 测试集 = walk-forward OOS（每个点都是"当时模型没见过"的样本，无泄漏）；不用训练区。
- 买点 = OOS 候选日中 proba > 阈值(默认 0.5)。
- 着色：命中 GT(SL7±2)=绿↑✓ / 没中=红↑✗；蓝色方块 = GT 真底(SL7±2)。
- 去掉其它所有标注（笔/中枢/分型/交易/Swing/Breadth/VIX/EMA），只留 K 线 + GT + 买点。

用法：python scripts/show_model_predictions.py --version v5_pa --thr 0.5 --port 9873
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from src.data_loader import load_data
from src.interactive_chart import show_interactive_chart
from src.indicators import detect_swing_lows
from experiments.configs import DATA_FILE

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    p = argparse.ArgumentParser(description="模型测试集(OOS)买点预测可视化")
    p.add_argument("--version", default="v5_pa", help="用哪个版本的 OOS 概率（oos_proba_{version}.csv）")
    p.add_argument("--model", default="trough_v1", help="模型代号（仅用于标题展示）")
    p.add_argument("--thr", type=float, default=0.5, help="买点概率阈值")
    p.add_argument("--port", type=int, default=9873)
    args = p.parse_args()

    oos_path = os.path.join(ROOT, "output", f"oos_proba_{args.version}.csv")
    if not os.path.exists(oos_path):
        raise FileNotFoundError(f"缺少 {oos_path}，先跑 walk-forward 生成 OOS 概率")
    oos = pd.read_csv(oos_path, parse_dates=["date"])
    oos["ds"] = oos["date"].dt.strftime("%Y-%m-%d")

    start = oos["date"].min().strftime("%Y-%m-%d")
    end = oos["date"].max().strftime("%Y-%m-%d")

    # K 线（OOS 区间）
    data = load_data(os.path.join(ROOT, DATA_FILE), start, end)

    # GT 真底 = SL7 ±2 个交易 bar（与训练标签 k=2 同口径），蓝色方块
    full = load_data(os.path.join(ROOT, DATA_FILE))
    dates_all = [d["date"] for d in full]
    closes_all = [d["close"] for d in full]
    sls = detect_swing_lows(closes_all, dates_all, 7)
    sl_set = set(s["date"] for s in sls)
    idx_of = {d: i for i, d in enumerate(dates_all)}
    gt_idx = set()
    for s in sls:
        i = idx_of[s["date"]]
        for j in range(i - 2, i + 3):
            if 0 <= j < len(dates_all):
                gt_idx.add(j)
    gt_dates = set(dates_all[j] for j in gt_idx if start <= dates_all[j] <= end)

    # 买点（proba > 阈值），按是否命中 GT 着色
    buys = oos[oos["proba"] > args.thr]
    hit = buys[buys["label"] == 1]["ds"].tolist()
    miss = buys[buys["label"] == 0]["ds"].tolist()
    n_buy = len(buys)
    prec = (buys["label"] == 1).mean() if n_buy else 0.0
    tot_pos = (oos["label"] == 1).sum()
    rec = (buys["label"] == 1).sum() / tot_pos if tot_pos else 0.0

    swing_lows = {
        "gtb": [{"date": d} for d in sorted(gt_dates)],
        "buyhit": [{"date": d} for d in hit],
        "buymiss": [{"date": d} for d in miss],
    }

    metrics = {"ema_series": [], "trade_log": [], "total_return": 0.0,
               "sharpe_ratio": 0.0, "max_drawdown": 0.0, "rsi_v2": {}}

    header_note = (
        f'<div class="stat">测试集(OOS) <span>{start}~{end}</span></div>'
        f'<div class="stat">阈值 <span>{args.thr}</span></div>'
        f'<div class="stat">买点 <span>{n_buy}</span></div>'
        f'<div class="stat">命中真底(精确率) <span>{prec:.1%}</span></div>'
        f'<div class="stat">召回 <span>{rec:.1%}</span></div>'
        '<div class="stat">绿↑命中 / 红↑没中 · 蓝方块=GT真底</div>'
    )
    title = f"{args.model} 测试集买点预测（{args.version}, thr={args.thr}）"

    print(f"OOS {start}~{end} | 买点 {n_buy}（命中 {len(hit)} / 没中 {len(miss)}）| "
          f"精确率 {prec:.1%} 召回 {rec:.1%} | GT真底 {len(gt_dates)}")

    # 独立输出目录，避免覆盖 9870 的 czsc 图
    out_dir = os.path.join(ROOT, "output", "pred")
    show_interactive_chart(data, metrics, title=title, port=args.port,
                           output_dir=out_dir, show_trades=False,
                           swing_lows=swing_lows, header_note=header_note)


if __name__ == "__main__":
    main()
