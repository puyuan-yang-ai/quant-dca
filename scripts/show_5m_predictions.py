# -*- coding: utf-8 -*-
"""
5 分钟验证图：在 5m K 线上叠加 中枢(箱体) + 最佳配置预测的底部 + 真实底部，供人工核对。

- 箱体：每个下跌用例的中枢矩形（紫框，来自 samples.json 的 box_sdt/edt/zg/zd）。
- 预测底部：最佳配置（第1次低9、系数2.5）——在 TD级别=L×系数 上找到的低9，其时间标到 5m 图（红▼）。
- 真实底部：蓝▲（对照预测准不准）。
为减少杂乱，默认只画 跌幅≥1% 且 箱体级别≥30m 的用例。

用法：
  python scripts/show_5m_predictions.py --start "2026-06-20" --end "2026-06-27"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import td_bottom_experiment as ex  # noqa: E402

DATA_DIR = REPO_ROOT / "data" / "intraday"
COEF, COUNT, OCC = 2.5, 9, 1            # 最佳配置
MIN_DROP, MIN_BOX_LEVEL = 0.01, 30      # 过滤：减少杂乱


def _pred_bottom(base, s):
    """最佳配置预测的底部 (time, low)；无信号返回 (None,None)。"""
    df = ex._td_df(base, ex._td_level(s["pullback_level"], COEF))
    th, tb = pd.Timestamp(s["rally_t1"]), pd.Timestamp(s["bottom_t"])
    win = df[(df["时间"] >= th) & (df["时间"] <= tb + pd.Timedelta(days=1))]
    sig = win[win["buy_setup"] == COUNT]
    if len(sig) < OCC:
        return None, None
    pos = sig.index[OCC - 1]
    return df.loc[pos, "时间"], float(df.loc[pos, "最低价"])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2026-06-20")
    p.add_argument("--end", default="2026-06-27")
    p.add_argument("--out", type=Path, default=DATA_DIR / "verify_5m.png")
    args = p.parse_args()
    start, end = pd.Timestamp(args.start), pd.Timestamp(args.end)

    base = pd.read_csv(DATA_DIR / "ESF_5m.csv", parse_dates=["时间"]).set_index("时间")
    samples = json.loads((DATA_DIR / "samples.json").read_text())

    view = base[(base.index >= start) & (base.index <= end)].reset_index()
    n = len(view)
    ts = view["时间"].to_numpy()

    def pos(t):
        i = int(np.searchsorted(ts, np.datetime64(pd.Timestamp(t))))
        return min(max(i, 0), n - 1)

    fig, ax = plt.subplots(figsize=(18, 8))
    for i, r in view.iterrows():
        c = "#26a69a" if r["收盘价"] >= r["开盘价"] else "#ef5350"
        ax.plot([i, i], [r["最低价"], r["最高价"]], color=c, lw=0.7, zorder=1)
        ax.plot([i, i], [r["开盘价"], r["收盘价"]], color=c, lw=2.0, zorder=1)

    drawn_box, drawn_bottom = set(), set()
    npred = nhit = 0
    for s in samples:
        if ex._drop_pct(s) < MIN_DROP or s["level"] < MIN_BOX_LEVEL:
            continue
        bsdt, bedt = pd.Timestamp(s["box_sdt"]), pd.Timestamp(s["box_edt"])
        if bedt < start or bsdt > end:
            continue
        # 箱体矩形（去重）
        bkey = (s["box_sdt"], s["box_edt"], s["box_zg"], s["box_zd"])
        if bkey not in drawn_box:
            drawn_box.add(bkey)
            x0, x1 = pos(bsdt), pos(bedt)
            ax.add_patch(Rectangle((x0, s["box_zd"]), max(x1 - x0, 0.5), s["box_zg"] - s["box_zd"],
                                   facecolor="#9b59b6", alpha=0.10, edgecolor="#9b59b6", lw=1, zorder=0))
        # 真实底部（去重）
        bt = pd.Timestamp(s["bottom_t"])
        if start <= bt <= end and s["bottom_t"] not in drawn_bottom:
            drawn_bottom.add(s["bottom_t"])
            ax.scatter([pos(bt)], [s["bottom_p"]], marker="^", color="#2962ff", s=70, zorder=5)
        # 预测底部
        pt, pp = _pred_bottom(base, s)
        if pt is not None and start <= pt <= end:
            npred += 1
            ax.scatter([pos(pt)], [pp], marker="v", color="#d50000", s=70, zorder=6)
            if s.get("bottom_p"):  # 预测距真实底 ≤ 1% 价格 视为"贴底"(粗略)
                if abs(pp - s["bottom_p"]) / s["bottom_p"] <= 0.005:
                    nhit += 1

    k = max(1, n // 10)
    ticks = list(range(0, n, k))
    ax.set_xticks(ticks)
    ax.set_xticklabels([pd.Timestamp(ts[i]).strftime("%m-%d\n%H:%M") for i in ticks])
    ax.set_title(f"ES=F 5m  {start:%m-%d} ~ {end:%m-%d}  | 紫框=中枢(箱体)  "
                 f"红▼=预测底(第1次低9·系数2.5)  蓝▲=真实底  (跌幅≥1%,箱体≥30m)")
    ax.set_ylabel("Price")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=120)
    plt.close(fig)
    print(f"已保存 {args.out}  | 区间内预测底 {npred} 个")


if __name__ == "__main__":
    main()
