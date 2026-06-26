"""
【权威评估脚本】用 label 列（训练口径=评估口径）评估抓底 Precision/Recall。

⭐ 这是评估抓底模型的【正确】方式：直接用 sl_proximity 生成的 label 列做真值，
   而非另造"几何比对"（信号日 vs swing low 中心 ±k 天）——后者口径与训练不一致，
   会夸大低 N 的 Recall，导致相反的错误结论（详见 diagnosis.md §11）。

对每个 N：walk-forward 拼接样本外概率 → 用 label 列在多个阈值下算 Precision/Recall。

用法:
  python -m ml.research.eval_by_label                  # N=1..5, 阈值 0.30/0.35/0.40
  python -m ml.research.eval_by_label --ns 2 --thrs 0.30 0.35 0.40 0.45
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


def _build(method, fm_, **kw):
    labeled = _orig(n_days=_CURRENT_N["n"], method=method, **kw)
    spy = load_spy()
    data, cols = fm_.build_features(labeled, spy)
    return data.dropna(subset=cols).reset_index(drop=True), cols


te._build_dataset = _build
import ml.eval_walkforward as ewf  # noqa: E402
ewf._build_dataset = _build
from ml.eval_walkforward import run_walkforward  # noqa: E402


def run(ns=(1, 2, 3, 4, 5), thrs=(0.30, 0.35, 0.40), folds=4):
    print("=" * 96)
    print("  抓底评估（label 列口径 = 训练口径，权威）")
    print("=" * 96)
    header = f"{'N':>2} {'候选':>5} {'真底':>5} {'基线P':>6} {'AUC':>6}"
    for t in thrs:
        header += f" | {('@'+format(t,'.2f')+' P/R'):>13}"
    print(header)
    print("-" * 96)

    rows = []
    for n in ns:
        _CURRENT_N["n"] = n
        wf = run_walkforward(version_tag=f"evallabel_n{n}", n_folds=folds)
        oos = wf["oos"].reset_index(drop=True)
        y = oos["label"].values
        proba = oos["proba"].values
        pos = int(y.sum())
        line = f"{n:>2} {len(oos):>5} {pos:>5} {y.mean()*100:>5.1f}% {wf['overall_auc']:>6.3f}"
        rec = {"N": n, "candidates": len(oos), "true_bottoms": pos,
               "baseline_p": float(y.mean()), "auc": wf["overall_auc"]}
        for t in thrs:
            m = proba > t
            if m.sum() == 0:
                p = r = 0.0
            else:
                p = y[m].mean(); r = y[m].sum() / pos
            line += f" | {p*100:>5.1f}%/{r*100:>4.0f}%"
            rec[f"p@{t}"] = p; rec[f"r@{t}"] = r
        print(line)
        rows.append(rec)

    print("=" * 96)
    print("基线P = 候选池里 label=1 占比（不用ML时的抓底命中率）。N越大基线P越高 = 高门槛候选本身更靠近底部。")
    out = ROOT / "output" / "eval_by_label.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"[Output] {out}")
    return pd.DataFrame(rows)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ns", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    p.add_argument("--thrs", type=float, nargs="+", default=[0.30, 0.35, 0.40])
    p.add_argument("--folds", type=int, default=4)
    args = p.parse_args()
    run(ns=tuple(args.ns), thrs=tuple(args.thrs), folds=args.folds)


if __name__ == "__main__":
    main()
