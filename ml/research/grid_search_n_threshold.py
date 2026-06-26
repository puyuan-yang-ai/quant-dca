"""
⚠️ 口径警告（2026-06-27）：本脚本用"几何比对"（信号日 vs swing low 中心 ±k 天）算事件级 P/R，
   与训练 label 列口径不一致，会夸大低 N 的 Recall，曾误推"N=1 最优"。
   **正确评估请用 ml/research/eval_by_label.py（label 口径）。** 本脚本仅作历史/弯路参考。
   阈值维度结论（0.35）不受影响仍成立；N 维度结论以 eval_by_label / diagnosis.md §11 为准。

N × 阈值 二维网格搜索（事件级 F1 选优）。

对每个 N：walk-forward 拼接 OOS 概率 → 在该 N 下扫所有阈值，算事件级 Precision/Recall/F1。
真底/命中口径与 GT 一致：swing_low(sl_n) ± k 天。
固定 sl_n=7, k=3（最克制，避免过拟合）。

输出 N×阈值 的事件F1矩阵 + 全局最优 + 次优差距（判断最优是否稳健）。

用法:
  python -m ml.research.grid_search_n_threshold
  python -m ml.research.grid_search_n_threshold --ns 1 2 3 4 5 --thr-min 0.20 --thr-max 0.60
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import ml.train_export as te
from ml.labeling import run as run_labeling, load_spy
from src.indicators import detect_swing_lows

_CURRENT_N = {"n": 2}
_orig = run_labeling


def _build_dataset_param(method, features_module, **kw):
    labeled = _orig(n_days=_CURRENT_N["n"], method=method, **kw)
    spy_df = load_spy()
    data, cols = features_module.build_features(labeled, spy_df)
    return data.dropna(subset=cols).reset_index(drop=True), cols


te._build_dataset = _build_dataset_param
import ml.eval_walkforward as ewf  # noqa: E402
ewf._build_dataset = _build_dataset_param
from ml.eval_walkforward import run_walkforward  # noqa: E402


def _event_pr(sig_dates, sl_in, total_bottoms, k):
    sl_arr = sl_in.values.astype("datetime64[D]")
    sig_arr = pd.to_datetime(pd.Series(sig_dates)).values.astype("datetime64[D]")
    if len(sig_arr) == 0:
        return float("nan"), 0.0, 0
    hit = sum(1 for d in sig_arr if len(sl_arr) and (np.abs((sl_arr - d).astype(int)) <= k).any())
    prec = hit / len(sig_arr)
    caught = sum(1 for b in sl_arr if (np.abs((sig_arr - b).astype(int)) <= k).any())
    rec = caught / total_bottoms if total_bottoms else float("nan")
    return prec, rec, caught


def run(ns=(1, 2, 3, 4, 5), thr_min=0.20, thr_max=0.60, step=0.05, sl_n=7, k=3, folds=4):
    spy = load_spy()
    sl = detect_swing_lows(spy["close"].tolist(),
                           spy["date"].dt.strftime("%Y-%m-%d").tolist(), sl_n)
    sl_dates = pd.to_datetime([s["date"] for s in sl])

    thresholds = np.round(np.arange(thr_min, thr_max + 1e-9, step), 2)
    results = []

    for n in ns:
        _CURRENT_N["n"] = n
        wf = run_walkforward(version_tag=f"grid_n{n}", n_folds=folds)
        oos = wf["oos"].reset_index(drop=True)
        oos_dates = pd.to_datetime(oos["date"])
        proba = oos["proba"].values
        lo, hi = oos_dates.min(), oos_dates.max()
        sl_in = sl_dates[(sl_dates >= lo) & (sl_dates <= hi)]
        total = len(sl_in)
        for thr in thresholds:
            mask = proba > thr
            sig_dates = oos_dates[mask]
            p, r, caught = _event_pr(sig_dates, sl_in, total, k)
            f1 = (2 * p * r / (p + r)) if (p and r and (p + r) > 0) else 0.0
            results.append({"N": n, "threshold": float(thr), "n_signal": int(mask.sum()),
                            "ev_precision": p, "ev_recall": r, "caught": caught, "ev_f1": f1})

    df = pd.DataFrame(results)

    # F1 矩阵
    pivot = df.pivot(index="N", columns="threshold", values="ev_f1")
    print("\n" + "=" * 80)
    print("  N × 阈值  事件级 F1 矩阵（越高越好；真底=swing_low(7)±3）")
    print("=" * 80)
    print(pivot.round(3).to_string())

    # 全局最优 + 次优们
    top = df.sort_values("ev_f1", ascending=False).head(6).reset_index(drop=True)
    print("\n  Top-6 配置（看最优是否稳健：若与第1名差距很小=噪声级，别迷信单一最优）")
    print(f"  {'排名':>3} {'N':>3} {'阈值':>5} {'事件F1':>7} {'Precision':>9} {'Recall':>7} {'信号数':>6} {'抓到底':>6}")
    for i, row in top.iterrows():
        print(f"  {i+1:>3} {int(row['N']):>3} {row['threshold']:>5.2f} {row['ev_f1']:>7.3f} "
              f"{row['ev_precision']*100:>8.1f}% {row['ev_recall']*100:>6.1f}% "
              f"{int(row['n_signal']):>6} {int(row['caught']):>6}")
    print("=" * 80)
    best = top.iloc[0]
    gap = top.iloc[0]['ev_f1'] - top.iloc[4]['ev_f1']
    print(f"\n  全局最优: N={int(best['N'])} 阈值={best['threshold']:.2f}  事件F1={best['ev_f1']:.3f}")
    print(f"  第1名与第5名 F1 差距 = {gap:.3f}  "
          f"{'→ 差距极小,最优不稳健,优先按偏好(机会多选低N)选' if gap < 0.02 else '→ 差距明显,最优可信'}")

    out = ROOT / "output" / "grid_search_n_threshold.csv"
    df.to_csv(out, index=False)
    print(f"  [Output] {out}")
    return df


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ns", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    p.add_argument("--thr-min", type=float, default=0.20)
    p.add_argument("--thr-max", type=float, default=0.60)
    p.add_argument("--step", type=float, default=0.05)
    p.add_argument("--folds", type=int, default=4)
    args = p.parse_args()
    run(ns=tuple(args.ns), thr_min=args.thr_min, thr_max=args.thr_max, step=args.step, folds=args.folds)


if __name__ == "__main__":
    main()
