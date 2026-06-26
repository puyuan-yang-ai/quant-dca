"""
阈值扫描 —— 用 label 列（训练口径=评估口径）算抓底 Precision/Recall + 信号簇。

口径修正（2026-06-27）：P/R 直接用训练 label 列（sl_proximity 生成），
不再用"几何比对"（信号日 vs swing low 中心 ±k），保证评估口径=训练口径。
（几何比对会夸大 Recall，曾导致错误结论，详见 diagnosis.md §11。）

第一性原理：
  - 目的 = 抓"局部低点"。纯阈值过滤（概率 > 阈值即信号），连续加仓由人工把关。
  - Precision = 放行信号中 label=1 占比（准）；Recall = 抓到的 label=1 / 全部 label=1（多）。
  - 信号簇 = 连续信号日并簇后的批次数 —— 此指标【口径无关】，衡量"连续加仓"程度，
    揭示"阈值过低反而黏连成大簇=连续加仓"的洞察。

用法：
  python -m ml.research.sweep_threshold_event            # 默认 N=2
  python -m ml.research.sweep_threshold_event --n 2
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


def _count_clusters(sorted_idx):
    """把信号的整数位置序列按'连续'并簇，返回簇数（口径无关）。"""
    if len(sorted_idx) == 0:
        return 0
    arr = np.sort(sorted_idx)
    return 1 + int((np.diff(arr) > 1).sum())


def run(n=2, folds=4):
    _CURRENT_N["n"] = n
    wf = run_walkforward(version_tag=f"thr_n{n}", n_folds=folds)
    oos = wf["oos"].reset_index(drop=True)
    y = oos["label"].values
    proba = oos["proba"].values
    total_pos = int(y.sum())  # 真底总数 = label=1 数量

    print("\n" + "=" * 90)
    print(f"  阈值扫描 N={n}  真底(label=1)={total_pos}  候选={len(oos)}  "
          f"基线P={y.mean()*100:.1f}%  （label 口径）")
    print("=" * 90)
    print(f"{'阈值':>5} {'信号数':>6} {'信号簇':>6} | "
          f"{'命中(label=1)':>12} {'Precision':>10} | "
          f"{'抓到真底':>8} {'Recall':>8} | {'F1':>6}")
    print("-" * 90)

    rows = []
    for thr in np.round(np.arange(0.10, 0.71, 0.05), 2):
        mask = proba > thr
        n_sig = int(mask.sum())
        n_cluster = _count_clusters(np.where(mask)[0])
        if n_sig == 0:
            rows.append((thr, 0, 0, 0, 0.0, 0, 0.0, 0.0)); continue

        hit = int(y[mask].sum())              # 放行信号中 label=1 的个数
        prec = hit / n_sig                    # Precision（label 口径）
        rec = hit / total_pos if total_pos else float("nan")  # Recall
        f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
        rows.append((thr, n_sig, n_cluster, hit, prec, hit, rec, f1))
        print(f"{thr:>5.2f} {n_sig:>6} {n_cluster:>6} | "
              f"{hit:>12} {prec*100:>9.1f}% | {hit:>8} {rec*100:>7.1f}% | {f1:>6.3f}")

    print("=" * 90)
    print("解读：")
    print("- Precision/Recall 用 label 列（训练口径=评估口径，权威）")
    print("- 信号簇【口径无关】：连续信号并簇的批次数。阈值过低→信号黏连成大簇=连续加仓")
    print("- 找 F1 高且信号簇可接受的阈值，即兼顾多与准、又不连续加仓的实盘落点")

    df = pd.DataFrame(rows, columns=["threshold", "n_signal", "n_cluster", "hit",
                                     "precision", "caught", "recall", "f1"])
    out = ROOT / "output" / f"sweep_threshold_event_n{n}.csv"
    df.to_csv(out, index=False)
    print(f"[Output] {out}")
    return df


def main():
    p = argparse.ArgumentParser(description="阈值扫描（label 口径 P/R + 信号簇）")
    p.add_argument("--n", type=int, default=2, help="NDay 门槛")
    p.add_argument("--folds", type=int, default=4)
    args = p.parse_args()
    run(n=args.n, folds=args.folds)


if __name__ == "__main__":
    main()
