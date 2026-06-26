"""
N=1 vs N=2 曲线对比图（label 口径：抓底 Precision/Recall/F1 + 信号簇 vs 阈值）。

口径修正（2026-06-27）：P/R/F1 用训练 label 列（不再用几何比对）。
label 口径下结论：N=2 略优于 N=1（@0.35 P/R 双优），详见 diagnosis.md §11。
信号簇为口径无关指标，衡量连续加仓程度。

用法: python -m ml.research.plot_n1_vs_n2
输出: output/n1_vs_n2_event.png
"""
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


def _clusters(pos):
    if len(pos) == 0:
        return 0
    a = np.sort(pos)
    return 1 + int((np.diff(a) > 1).sum())


def _scan(n, thrs=None):
    """用 label 列算 P/R/F1 + 信号簇。"""
    _CURRENT_N["n"] = n
    wf = run_walkforward(version_tag=f"n1n2_{n}", n_folds=4)
    oos = wf["oos"].reset_index(drop=True)
    y = oos["label"].values
    proba = oos["proba"].values
    total = int(y.sum())
    rows = []
    for thr in thrs:
        mask = proba > thr
        pos = np.where(mask)[0]
        n_sig = int(mask.sum())
        if n_sig == 0:
            rows.append((thr, 0, 0, np.nan, 0, 0)); continue
        hit = int(y[mask].sum())
        p = hit / n_sig; r = hit / total
        f1 = 2*p*r/(p+r) if (p+r) > 0 else 0
        rows.append((thr, n_sig, _clusters(pos), p, r, f1))
    return pd.DataFrame(rows, columns=["thr", "n_sig", "cluster", "prec", "rec", "f1"]), total


def run():
    thrs = np.round(np.arange(0.15, 0.66, 0.05), 2)

    d1, t1 = _scan(1, thrs=thrs)
    d2, t2 = _scan(2, thrs=thrs)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
    # 左: F1 / Precision / Recall
    ax1.plot(d1["thr"], d1["f1"]*100, "o-", color="seagreen", lw=2.2, label=f"N=1 F1 (真底{t1})")
    ax1.plot(d2["thr"], d2["f1"]*100, "s-", color="darkorange", lw=2.2, label=f"N=2 F1 (真底{t2})")
    ax1.plot(d1["thr"], d1["rec"]*100, "o--", color="seagreen", alpha=0.5, label="N=1 Recall")
    ax1.plot(d2["thr"], d2["rec"]*100, "s--", color="darkorange", alpha=0.5, label="N=2 Recall")
    ax1.plot(d1["thr"], d1["prec"]*100, "o:", color="seagreen", alpha=0.5, label="N=1 Precision")
    ax1.plot(d2["thr"], d2["prec"]*100, "s:", color="darkorange", alpha=0.5, label="N=2 Precision")
    ax1.axvline(0.35, color="gray", ls=":", alpha=0.7)
    ax1.set_xlabel("概率阈值"); ax1.set_ylabel("%")
    ax1.set_title("N=1 vs N=2 F1/Recall/Precision (label口径)\n(实线F1 虚线Recall 点线Precision)")
    ax1.legend(fontsize=8, ncol=2); ax1.grid(alpha=0.3)

    # 右: 信号数 & 信号簇(加仓批次)
    ax2.plot(d1["thr"], d1["n_sig"], "o-", color="seagreen", label="N=1 信号数")
    ax2.plot(d2["thr"], d2["n_sig"], "s-", color="darkorange", label="N=2 信号数")
    ax2.plot(d1["thr"], d1["cluster"], "o--", color="seagreen", alpha=0.6, label="N=1 信号簇")
    ax2.plot(d2["thr"], d2["cluster"], "s--", color="darkorange", alpha=0.6, label="N=2 信号簇")
    ax2.axvline(0.35, color="gray", ls=":", alpha=0.7)
    ax2.set_xlabel("概率阈值"); ax2.set_ylabel("个数")
    ax2.set_title("N=1 vs N=2 信号数 / 信号簇\n(信号簇≈人工需把关的加仓批次)")
    ax2.legend(fontsize=8); ax2.grid(alpha=0.3)

    plt.tight_layout()
    out = ROOT / "output" / "n1_vs_n2_event.png"
    plt.savefig(out, dpi=150, bbox_inches="tight"); plt.close()
    # 打印 0.35 处对比
    r1 = d1[d1["thr"] == 0.35].iloc[0]; r2 = d2[d2["thr"] == 0.35].iloc[0]
    print("\n@阈值0.35 对比:")
    print(f"  N=1: F1={r1['f1']:.3f} P={r1['prec']*100:.1f}% R={r1['rec']*100:.1f}% 信号{int(r1['n_sig'])} 簇{int(r1['cluster'])}")
    print(f"  N=2: F1={r2['f1']:.3f} P={r2['prec']*100:.1f}% R={r2['rec']*100:.1f}% 信号{int(r2['n_sig'])} 簇{int(r2['cluster'])}")
    print(f"[Output] {out}")
    return out


if __name__ == "__main__":
    run()
