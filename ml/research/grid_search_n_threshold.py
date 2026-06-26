"""
N × 阈值 二维网格搜索（label 口径 F1 选优）。

口径修正（2026-06-27）：P/R/F1 直接用训练 label 列（不再用几何比对），
保证评估口径=训练口径。结论：N=2 @0.35 最优（详见 diagnosis.md §11）。

对每个 N：walk-forward 拼接 OOS 概率 → 在该 N 下扫所有阈值，用 label 列算 Precision/Recall/F1。

输出 N×阈值 的 F1矩阵 + 全局最优 + 次优差距（判断最优是否稳健）。

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


def _label_pr(y, mask, total_pos):
    """用 label 列算 (precision, recall, caught)。"""
    sel = y[mask]
    if len(sel) == 0:
        return float("nan"), 0.0, 0
    caught = int(sel.sum())
    prec = caught / len(sel)
    rec = caught / total_pos if total_pos else float("nan")
    return prec, rec, caught


def run(ns=(1, 2, 3, 4, 5), thr_min=0.20, thr_max=0.60, step=0.05, folds=4):
    thresholds = np.round(np.arange(thr_min, thr_max + 1e-9, step), 2)
    results = []

    for n in ns:
        _CURRENT_N["n"] = n
        wf = run_walkforward(version_tag=f"grid_n{n}", n_folds=folds)
        oos = wf["oos"].reset_index(drop=True)
        y = oos["label"].values
        proba = oos["proba"].values
        total = int(y.sum())
        for thr in thresholds:
            mask = proba > thr
            p, r, caught = _label_pr(y, mask, total)
            f1 = (2 * p * r / (p + r)) if (p and r and (p + r) > 0) else 0.0
            results.append({"N": n, "threshold": float(thr), "n_signal": int(mask.sum()),
                            "ev_precision": p, "ev_recall": r, "caught": caught, "ev_f1": f1})

    df = pd.DataFrame(results)

    # F1 矩阵
    pivot = df.pivot(index="N", columns="threshold", values="ev_f1")
    print("\n" + "=" * 80)
    print("  N × 阈值  F1 矩阵（label 口径，越高越好）")
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
