"""
画 阈值 vs 事件Precision/Recall/信号簇 曲线图。
读 output/sweep_threshold_event_n{n}.csv（由 sweep_threshold_event.py 生成）。

用法:
  python -m ml.research.plot_threshold_event --n 2
输出: output/threshold_event_tradeoff_n{n}.png
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

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

_ZH = Path.home() / ".fonts" / "NotoSansSC-Regular.ttf"
if _ZH.exists():
    fm.fontManager.addfont(str(_ZH))
    plt.rcParams["font.family"] = fm.FontProperties(fname=str(_ZH)).get_name()
plt.rcParams["axes.unicode_minus"] = False


def run(n=2):
    csv = ROOT / "output" / f"sweep_threshold_event_n{n}.csv"
    if not csv.exists():
        raise FileNotFoundError(f"先跑 ml.research.sweep_threshold_event --n {n} 生成 {csv}")
    df = pd.read_csv(csv)
    df = df[df["n_signal"] > 0].reset_index(drop=True)

    thr = df["threshold"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

    # 左图: 事件 Precision / Recall / F1 vs 阈值
    ax1.plot(thr, df["ev_precision"] * 100, "o-", color="crimson", label="事件 Precision (准)")
    ax1.plot(thr, df["ev_recall"] * 100, "s-", color="steelblue", label="事件 Recall (多抓底)")
    ax1.plot(thr, df["ev_f1"] * 100, "^--", color="seagreen", lw=2, label="事件 F1 (综合)")
    best = df.loc[df["ev_f1"].idxmax()]
    ax1.axvline(best["threshold"], color="orange", ls=":", lw=2,
                label=f"F1最优 thr={best['threshold']:.2f}")
    ax1.scatter([best["threshold"]], [best["ev_f1"] * 100], color="orange", s=120, zorder=5)
    ax1.set_xlabel("概率阈值"); ax1.set_ylabel("百分比 (%)")
    ax1.set_title("阈值 vs 事件 Precision / Recall / F1\n(绿线峰值=兼顾'多'与'准'的最优点)")
    ax1.legend(fontsize=9); ax1.grid(alpha=0.3)

    # 右图: 信号数 与 信号簇 vs 阈值（连续加仓量级）
    ax2.bar(thr, df["n_signal"], width=0.018, alpha=0.35, color="gray", label="信号数(总)")
    ax2b = ax2.twinx()
    ax2b.plot(thr, df["n_cluster"], "D-", color="purple", label="信号簇数(加仓批次)")
    # 平均每簇天数 = 信号数 / 簇数，越大=越连续
    avg_len = df["n_signal"] / df["n_cluster"].replace(0, np.nan)
    ax2.plot(thr, avg_len * (df["n_signal"].max() / avg_len.max()), "x--", color="darkred",
             alpha=0.7, label="平均每簇天数(缩放)")
    ax2.set_xlabel("概率阈值"); ax2.set_ylabel("信号数")
    ax2b.set_ylabel("信号簇数")
    ax2.set_title("阈值 vs 信号数 / 信号簇 / 连续度\n(阈值过低→大片黏连=连续加仓; 适度抬高→信号更孤立)")
    lines = ax2.get_legend_handles_labels()[0] + ax2b.get_legend_handles_labels()[0]
    labels = ax2.get_legend_handles_labels()[1] + ax2b.get_legend_handles_labels()[1]
    ax2.legend(lines, labels, fontsize=8, loc="upper right")
    ax2.grid(alpha=0.3)

    plt.tight_layout()
    out = ROOT / "output" / f"threshold_event_tradeoff_n{n}.png"
    plt.savefig(out, dpi=150, bbox_inches="tight"); plt.close()
    print(f"[Output] {out}")
    print(f"F1最优阈值={best['threshold']:.2f}  Precision={best['ev_precision']*100:.1f}%  "
          f"Recall={best['ev_recall']*100:.1f}%  信号簇={int(best['n_cluster'])}")
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=2)
    args = p.parse_args()
    run(n=args.n)


if __name__ == "__main__":
    main()
