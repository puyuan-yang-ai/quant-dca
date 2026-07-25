# -*- coding: utf-8 -*-
"""
"识别低点"检测任务评估：在【共同样本外区间的全部交易日】上、对【共同 GT = SL7 ±2 bar】，
算各版本管线(过滤+模型)的 Precision / Recall / F1。

- 共同 universe = 三版 OOS 区间的交集内的所有交易日。
- 共同 GT(正样本) = 距某个 SL7 摆动低点 ≤2 个交易 bar 的 bar（含中心，5 根窗），与训练标签 k=2 同义。
- 预测为底 = 候选日中 proba > 阈值 的日子（非候选日=未预测=负）。
- 召回率分母 = 全 K 线 GT 真底（含被第一层过滤漏掉的）→ 体现整条管线的覆盖能力。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import pandas as pd
from ml.labeling import load_spy
from src.indicators import detect_swing_lows

VERS = ["v3_n2", "v5_pa", "v5_pa_c5"]


def main():
    spy = load_spy()
    dates = spy["date"].dt.strftime("%Y-%m-%d").tolist()
    close = spy["close"].tolist()
    sls = detect_swing_lows(close, dates, 7)
    sl_set = set(s["date"] for s in sls)
    sl_pos = [i for i, d in enumerate(dates) if d in sl_set]
    gt_pos = set()
    for p in sl_pos:
        for j in range(p - 2, p + 3):  # SL7 ±2（含中心，共5根）
            if 0 <= j < len(dates):
                gt_pos.add(j)
    gt_dates = set(dates[i] for i in gt_pos)

    oos = {}
    for v in VERS:
        df = pd.read_csv(os.path.join(ROOT, "output", f"oos_proba_{v}.csv"), parse_dates=["date"])
        df["ds"] = df["date"].dt.strftime("%Y-%m-%d")
        oos[v] = df

    lo = max(df["date"].min() for df in oos.values())
    hi = min(df["date"].max() for df in oos.values())
    los, his = lo.strftime("%Y-%m-%d"), hi.strftime("%Y-%m-%d")
    uni = [d for d in dates if los <= d <= his]
    gt_in = set(d for d in uni if d in gt_dates)

    print("=" * 72)
    print(f"  共同 OOS 窗口: {los} ~ {his}")
    print(f"  全 K 线交易日: {len(uni)}   GT 真底(SL7±2): {len(gt_in)} ({100*len(gt_in)/len(uni):.1f}%)")
    print("=" * 72)

    def prf(pred_dates):
        pred = set(pred_dates) & set(uni)
        tp = len(pred & gt_in)
        fp = len(pred - gt_in)
        fn = len(gt_in - pred)
        p = tp / (tp + fp) if (tp + fp) else float("nan")
        r = tp / (tp + fn) if (tp + fn) else float("nan")
        f = 2 * p * r / (p + r) if (p and r and p + r) else float("nan")
        return p, r, f, len(pred)

    print(f"\n  {'版本':<10}{'阈值':>8}{'Precision':>11}{'Recall':>9}{'F1':>8}{'预测买点':>9}")
    for v in VERS:
        df = oos[v]
        df = df[(df["ds"] >= los) & (df["ds"] <= his)]
        pf = df[df["proba"] > df["fold_threshold"]]["ds"]
        p, r, f, n = prf(pf)
        print(f"  {v:<10}{'fold':>8}{p:>11.3f}{r:>9.3f}{f:>8.3f}{n:>9}")
        for t in (0.4, 0.5, 0.6):
            pt = df[df["proba"] > t]["ds"]
            p, r, f, n = prf(pt)
            print(f"  {v:<10}{t:>8.1f}{p:>11.3f}{r:>9.3f}{f:>8.3f}{n:>9}")
        print("  " + "-" * 60)


if __name__ == "__main__":
    main()
