# -*- coding: utf-8 -*-
"""
路径A czsc 特征消融：A0/A1/A2/A3，全在 v5_pa(近底n30p05) universe + sl_proximity(k2) 标签。
统计口径：Precision/Recall 为主（fold阈值 + 0.4/0.5/0.6 对照），AUC 为辅，不看收益。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import numpy as np
import pandas as pd
from ml.eval_walkforward import run_walkforward

ARMS = [
    ("A0 base(21)", "v5_pa"),
    ("A1 +czsc布尔(22)", "v5_pa_c1"),
    ("A2 +czsc5列(26)", "v5_pa_c5"),
    ("A3 正交base+czsc", "v5_pa_orth"),
]


def pr_at(df, thr):
    """thr: 标量或与 df 等长数组。返回 (precision, recall, 预测买点数)。"""
    pred = df["proba"].values > thr
    y = df["label"].values
    tp = int((pred & (y == 1)).sum())
    pp = int(pred.sum())
    ap = int((y == 1).sum())
    prec = tp / pp if pp else float("nan")
    rec = tp / ap if ap else float("nan")
    return prec, rec, pp


def main():
    res = []
    for name, ver in ARMS:
        print("\n" + "#" * 56 + f"\n#  {name}  ({ver})\n" + "#" * 56)
        r = run_walkforward(version=ver, n_folds=4)
        df = pd.read_csv(os.path.join(ROOT, "output", f"oos_proba_{ver}.csv"), parse_dates=["date"])
        pr = {"fold": pr_at(df, df["fold_threshold"].values)}
        for t in (0.4, 0.5, 0.6):
            pr[t] = pr_at(df, t)
        res.append((name, r, df, pr))

    print("\n" + "=" * 78)
    print("  路径A czsc 消融 · 统计层（同 universe 近底n30p05, 标签 sl_proximity k2）")
    print("=" * 78)
    print(f"  {'臂':<18}{'AUC-ROC':>9}{'95% CI':>18}{'OOS_n':>8}{'正例率':>8}")
    for name, r, df, pr in res:
        ci = r["auc_ci"]
        print(f"  {name:<18}{r['overall_auc']:>9.4f}{f'({ci[0]:.3f},{ci[1]:.3f})':>18}"
              f"{len(df):>8}{df['label'].mean():>8.3f}")

    print("\n" + "=" * 78)
    print("  Precision / Recall（预测 label=1=真底；P=精确率 R=召回率 n=预测买点数）")
    print("=" * 78)
    print(f"  {'臂':<18}{'fold阈值':>20}{'thr0.4':>16}{'thr0.5':>16}{'thr0.6':>16}")
    for name, r, df, pr in res:
        def cell(k):
            p, rc, n = pr[k]
            return f"P{p:.2f}/R{rc:.2f}/{n}"
        print(f"  {name:<18}{cell('fold'):>20}{cell(0.4):>16}{cell(0.5):>16}{cell(0.6):>16}")

    # czsc 增量（A2 - A0）
    a0 = res[0][1]["overall_auc"]
    a2 = res[2][1]["overall_auc"]
    print("\n" + "-" * 78)
    print(f"  czsc 增量(A2 - A0) AUC: {a0:.4f} → {a2:.4f}  (Δ {a2 - a0:+.4f})")
    print("-" * 78)


if __name__ == "__main__":
    main()
