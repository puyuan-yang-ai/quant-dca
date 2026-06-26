"""
NDay 门槛遍历研究脚本 —— 以【抓底 Precision + Recall】为核心指标。

背景：评判"抓底模型"不能用收益率（SPY 长牛，买越多越赚，收益率对抓底系统性不利）。
正确尺子 = 抓底命中率(Precision) + 底部覆盖率(Recall)，真值 GT = sl_proximity 标签(swing low ± k 天)。

本脚本对每个 N ∈ sweep：
  walk-forward 拼接样本外概率 → 对比 NDay 信号本身(基线) vs ML 放行后的 Precision/Recall。
关键洞察：
  - N 越大，单点抓底 Precision 越高，但候选池里的"真底总数"越少(门槛在源头过滤掉机会) → Recall 上限被压低。
  - 因此最优 N 是 Precision/Recall 的偏好权衡，不是越大越好。

用法：
  python -m ml.research.sweep_ndays_precision_recall                 # 默认遍历 N=1..5
  python -m ml.research.sweep_ndays_precision_recall --ns 1 2 3      # 自定义 N 列表
  python -m ml.research.sweep_ndays_precision_recall --folds 4

只读：不修改任何项目文件，通过 monkey-patch 把写死的 n_days=5 改成循环变量。
副产物：output/oos_proba_pr_n{N}.csv（样本外概率，可复用）。
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

_CURRENT_N = {"n": 5}
_orig_run_labeling = run_labeling


def _build_dataset_param(method, features_module, **labeling_kwargs):
    """复刻 train_export._build_dataset，但 n_days 用循环变量而非写死的 5。"""
    labeled = _orig_run_labeling(n_days=_CURRENT_N["n"], method=method, **labeling_kwargs)
    spy_df = load_spy()
    data, feature_cols = features_module.build_features(labeled, spy_df)
    data = data.dropna(subset=feature_cols).reset_index(drop=True)
    return data, feature_cols


# 同时替换 train_export 与 eval_walkforward 两处绑定的引用
te._build_dataset = _build_dataset_param
import ml.eval_walkforward as ewf  # noqa: E402
ewf._build_dataset = _build_dataset_param
from ml.eval_walkforward import run_walkforward  # noqa: E402


def _pr(y, mask, total_pos):
    """返回 (precision, recall, caught) for a boolean selection mask."""
    sel = y[mask]
    if len(sel) == 0:
        return float("nan"), float("nan"), 0
    caught = int(sel.sum())
    precision = caught / len(sel)
    recall = caught / total_pos if total_pos else float("nan")
    return precision, recall, caught


def _topk_mask(proba, pct):
    n = len(proba)
    k = max(1, int(n * pct))
    idx = np.argsort(-proba)[:k]
    m = np.zeros(n, dtype=bool)
    m[idx] = True
    return m


def run(ns=(1, 2, 3, 4, 5), folds=4):
    out_dir = ROOT / "output"
    out_dir.mkdir(exist_ok=True)

    rows = []
    for n in ns:
        _CURRENT_N["n"] = n
        wf = run_walkforward(version_tag=f"pr_n{n}", n_folds=folds)
        oos = wf["oos"].reset_index(drop=True)
        y = oos["label"].values
        proba = oos["proba"].values
        total_pos = int(y.sum())

        base_p = float(y.mean())  # 基线 precision = 候选本身命中率（recall=100%）
        m_thr = proba > oos["fold_threshold"].values
        p_thr, r_thr, c_thr = _pr(y, m_thr, total_pos)
        p20, r20, c20 = _pr(y, _topk_mask(proba, 0.20), total_pos)
        p30, r30, c30 = _pr(y, _topk_mask(proba, 0.30), total_pos)

        rows.append({
            "N": n, "candidates": len(oos), "true_bottoms": total_pos,
            "auc": wf["overall_auc"], "baseline_precision": base_p,
            "thr_p": p_thr, "thr_r": r_thr, "thr_caught": c_thr,
            "top20_p": p20, "top20_r": r20, "top20_caught": c20,
            "top30_p": p30, "top30_r": r30, "top30_caught": c30,
        })

    df = pd.DataFrame(rows)
    csv_path = out_dir / "sweep_precision_recall_summary.csv"
    df.to_csv(csv_path, index=False)

    print("\n" + "=" * 104)
    print("  NDay 门槛遍历 — 抓底 Precision / Recall（收益率已弃用）")
    print("=" * 104)
    print(f"{'N':>3} {'候选':>6} {'真底数':>6} {'AUC':>6} {'基线P':>6} | "
          f"{'阈值放行 P/R/抓到':>20} | {'Top20% P/R/抓到':>20} | {'Top30% P/R/抓到':>20}")
    print("-" * 104)
    for r in rows:
        print(f"{r['N']:>3} {r['candidates']:>6} {r['true_bottoms']:>6} {r['auc']:>6.3f} "
              f"{r['baseline_precision']*100:>5.0f}% | "
              f"{r['thr_p']*100:>4.0f}%/{r['thr_r']*100:>3.0f}%/{r['thr_caught']:>4} | "
              f"{r['top20_p']*100:>4.0f}%/{r['top20_r']*100:>3.0f}%/{r['top20_caught']:>4} | "
              f"{r['top30_p']*100:>4.0f}%/{r['top30_r']*100:>3.0f}%/{r['top30_caught']:>4}")
    print("=" * 104)
    print("解读：")
    print("- 真底数：该 N 候选池里 GT 正样本总数。N 越大此数越小 → 门槛在源头过滤掉底部机会(压低 Recall 上限)")
    print("- P=抓底准确度  R=底部覆盖率  抓到=命中的真底个数")
    print("- 基线P 对应 Recall=100%(全买不漏)。ML 提升 P 必然牺牲 R，最优 N 取决于你对 P/R 的偏好")
    print(f"- [Output] {csv_path}")
    return df


def main():
    p = argparse.ArgumentParser(description="NDay 门槛遍历：抓底 Precision/Recall")
    p.add_argument("--ns", type=int, nargs="+", default=[1, 2, 3, 4, 5], help="要遍历的 N 列表")
    p.add_argument("--folds", type=int, default=4, help="walk-forward 折数")
    args = p.parse_args()
    run(ns=tuple(args.ns), folds=args.folds)


if __name__ == "__main__":
    main()
