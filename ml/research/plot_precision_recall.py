"""
画各 NDay 门槛的 抓底 Precision-Recall 权衡曲线 + F1/F2 综合分。

横轴 Recall(底部覆盖率)、纵轴 Precision(抓底命中率)，每条线是一个 N，
沿线扫描概率阈值。叠加基线点(全买: recall=100%, precision=正样本率)。
右图: 各 N 的最优 F1 / F2 综合分(F2 给 recall 双倍权重,贴合"宁可多抓"偏好)。

用法:
  python -m ml.research.plot_precision_recall
  python -m ml.research.plot_precision_recall --ns 1 2 3 4 5

输出: output/precision_recall_tradeoff.png
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from sklearn.metrics import precision_recall_curve

# 注册中文字体（避免图中中文乱码）
_ZH_FONT = Path.home() / ".fonts" / "NotoSansSC-Regular.ttf"
if _ZH_FONT.exists():
    fm.fontManager.addfont(str(_ZH_FONT))
    plt.rcParams["font.family"] = fm.FontProperties(fname=str(_ZH_FONT)).get_name()
plt.rcParams["axes.unicode_minus"] = False

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import ml.train_export as te
from ml.labeling import run as run_labeling, load_spy

_CURRENT_N = {"n": 5}
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


def _fbeta(p, r, beta):
    b2 = beta * beta
    denom = b2 * p + r
    return (1 + b2) * p * r / denom if denom > 0 else 0.0


def run(ns=(1, 2, 3, 4, 5), folds=4):
    out_dir = ROOT / "output"
    out_dir.mkdir(exist_ok=True)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
    cmap = plt.cm.viridis(np.linspace(0, 0.85, len(ns)))

    summary = []
    for color, n in zip(cmap, ns):
        _CURRENT_N["n"] = n
        wf = run_walkforward(version_tag=f"prcurve_n{n}", n_folds=folds)
        oos = wf["oos"]
        y = oos["label"].values
        proba = oos["proba"].values
        base = float(y.mean())

        prec, rec, thr = precision_recall_curve(y, proba)
        # precision_recall_curve 末点 recall=0,去掉便于看
        ax1.plot(rec, prec, color=color, lw=2, label=f"N={n} (真底{int(y.sum())}个, AUC={wf['overall_auc']:.3f})")
        ax1.scatter([1.0], [base], color=color, marker="x", s=60)  # 基线: 全买

        # 各阈值下 F1/F2, 取最优
        f1s = [_fbeta(p, r, 1) for p, r in zip(prec, rec)]
        f2s = [_fbeta(p, r, 2) for p, r in zip(prec, rec)]
        best_f1, best_f2 = max(f1s), max(f2s)
        # 最优F2对应的P/R
        bi = int(np.argmax(f2s))
        summary.append({"N": n, "baseline_p": base, "best_f1": best_f1, "best_f2": best_f2,
                        "f2_precision": prec[bi], "f2_recall": rec[bi],
                        "f2_threshold": thr[bi] if bi < len(thr) else 1.0})

    ax1.axhline(0, color="gray", lw=0.5)
    ax1.set_xlabel("Recall (底部覆盖率 = 抓到的真底 / 全部真底)")
    ax1.set_ylabel("Precision (抓底命中率 = 抓对的 / 模型说是底的)")
    ax1.set_title("抓底 Precision-Recall 权衡曲线\n(x标记=基线全买; 线越靠右上越好)")
    ax1.legend(fontsize=8, loc="upper right")
    ax1.grid(alpha=0.3)

    sdf = pd.DataFrame(summary)
    x = np.arange(len(sdf))
    w = 0.35
    ax2.bar(x - w/2, sdf["best_f1"], w, label="最优 F1 (P/R 同权)", color="steelblue")
    ax2.bar(x + w/2, sdf["best_f2"], w, label="最优 F2 (R 双倍权重)", color="coral")
    ax2.set_xticks(x)
    ax2.set_xticklabels([f"N={n}" for n in sdf["N"]])
    ax2.set_ylabel("综合分")
    ax2.set_title("各 N 的最优 F1 / F2 综合分\n(F2 偏好高 Recall, 贴合'宁可多抓机会')")
    ax2.legend(fontsize=9)
    ax2.grid(alpha=0.3, axis="y")
    for xi, (f1, f2) in enumerate(zip(sdf["best_f1"], sdf["best_f2"])):
        ax2.text(xi - w/2, f1 + 0.005, f"{f1:.3f}", ha="center", fontsize=8)
        ax2.text(xi + w/2, f2 + 0.005, f"{f2:.3f}", ha="center", fontsize=8)

    plt.tight_layout()
    path = out_dir / "precision_recall_tradeoff.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()

    print("\n各 N 的最优 F1 / F2 综合分:")
    print(sdf.to_string(index=False))
    print(f"\n[Output] {path}")
    return sdf


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ns", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    p.add_argument("--folds", type=int, default=4)
    args = p.parse_args()
    run(ns=tuple(args.ns), folds=args.folds)


if __name__ == "__main__":
    main()
