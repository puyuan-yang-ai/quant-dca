# -*- coding: utf-8 -*-
"""
TD 九转可视化校验（在 K 线上标注 Setup 1–9 与 Countdown 1–13）。

用途：把 Python 实现的 TD 计数画到图上，供你对照 TradingView 的 TD Sequential 人工校验。
TD 在该级别**全历史**上计算（保证计数正确），只显示 --start ~ --end 区间。

用法：
    python scripts/show_td_sequential.py --level 90 \
        --start "2026-06-24 00:00" --end "2026-06-26 12:00"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.indicators.td_sequential import compute_td  # noqa: E402

DATA_DIR = REPO_ROOT / "data" / "intraday"
BASE_MINUTES = 5


def _load_level(prefix: str, minutes: int) -> pd.DataFrame:
    base = pd.read_csv(DATA_DIR / f"{prefix}_{BASE_MINUTES}m.csv", parse_dates=["时间"]).set_index("时间")
    if minutes == BASE_MINUTES:
        df = base.copy()
    else:
        df = base.resample(f"{minutes}min", label="left", closed="left").agg({
            "开盘价": "first", "最高价": "max", "最低价": "min",
            "收盘价": "last", "成交量": "sum",
        }).dropna(subset=["收盘价"])
    df = df.reset_index()
    td = compute_td(df["最高价"].tolist(), df["最低价"].tolist(), df["收盘价"].tolist())
    for k, v in td.items():
        df[k] = v
    return df


def main():
    parser = argparse.ArgumentParser(description="TD 九转可视化校验")
    parser.add_argument("--level", type=int, required=True, help="级别（分钟）")
    parser.add_argument("--start", required=True, help="显示起（北京时间）")
    parser.add_argument("--end", required=True, help="显示止（北京时间）")
    parser.add_argument("--prefix", default="ESF")
    parser.add_argument("--countdown", choices=["off", "a", "b", "both"], default="both",
                        help="Countdown 显示：a=方案A正统(橙) / b=方案B溢出(灰) / both / off")
    parser.add_argument("--out-dir", type=Path, default=DATA_DIR / "td_charts")
    args = parser.parse_args()

    show_a = args.countdown in ("a", "both")
    show_b = args.countdown in ("b", "both")

    start, end = pd.Timestamp(args.start), pd.Timestamp(args.end)
    df = _load_level(args.prefix, args.level)
    view = df[(df["时间"] >= start) & (df["时间"] <= end)].copy()
    if view.empty:
        print("区间内无数据"); sys.exit(1)

    fig, ax = plt.subplots(figsize=(14, 7))
    # K 线（简版：高低竖线 + 开收）
    for _, r in view.iterrows():
        t = r["时间"]
        up = r["收盘价"] >= r["开盘价"]
        c = "#26a69a" if up else "#ef5350"
        ax.plot([t, t], [r["最低价"], r["最高价"]], color=c, lw=0.8, zorder=1)
        ax.plot([t, t], [r["开盘价"], r["收盘价"]], color=c, lw=3, zorder=1)

    rng = view["最高价"].max() - view["最低价"].min()
    off = rng * 0.02

    for _, r in view.iterrows():
        t = r["时间"]
        bs = int(r["buy_setup"])
        # 买入 Setup 1–9 标在下方（蓝），9 高亮；溢出 10–13 标灰
        if 1 <= bs <= 9:
            ax.annotate(str(bs), (t, r["最低价"] - off), color="#2962ff",
                        fontsize=9 if bs == 9 else 7,
                        fontweight="bold" if bs == 9 else "normal",
                        ha="center", va="top")
            if bs == 9 and bool(r["buy_setup_perfected"]):
                ax.annotate("^", (t, r["最低价"] - off * 3), color="#2962ff",
                            fontsize=8, ha="center", va="top")
        elif show_b and 10 <= bs <= 13:  # 方案B：Setup 溢出（灰）
            ax.annotate(str(bs), (t, r["最低价"] - off), color="#999",
                        fontsize=7, ha="center", va="top")
        # 方案A：买入 Countdown 1–13（橙），13/complete 高亮
        cdv = int(r["buy_cd"])
        st = r["buy_cd_status"]
        if show_a and cdv >= 1:
            color = "#ff6d00"
            label = str(cdv)
            if st == "complete":
                label, color = "13v", "#d50000"
            elif st == "defer":
                label = "+"
            ax.annotate(label, (t, r["最低价"] - off * 5), color=color,
                        fontsize=9 if st == "complete" else 7,
                        fontweight="bold" if st == "complete" else "normal",
                        ha="center", va="top")
        if show_a and st in ("cancel", "recycle"):
            ax.annotate("R" if st == "recycle" else "X", (t, r["最高价"] + off),
                        color="#9b59b6", fontsize=8, ha="center", va="bottom")

    ax.set_title(f"ES=F {args.level}m  TD Sequential  {start:%m-%d %H:%M} ~ {end:%m-%d %H:%M} (Beijing)\n"
                 f"blue=BuySetup(^=perfected)  orange=BuyCountdown(+=defer 13v=complete)  "
                 f"gray=setup overshoot  purple R/X=recycle/cancel")
    ax.set_ylabel("Price")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d\n%H:%M"))
    ax.grid(alpha=0.25)
    fig.tight_layout()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = args.out_dir / f"td_{args.level}m.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    print(f"已保存 {path}")

    # 顺带打印区间内的关键事件，便于核对
    print("\n区间内 买入Setup=9 / Countdown 事件：")
    for _, r in view.iterrows():
        if int(r["buy_setup"]) == 9 or r["buy_cd_status"]:
            print(f"  {r['时间']}  setup={int(r['buy_setup'])} "
                  f"perf={bool(r['buy_setup_perfected'])} cd={int(r['buy_cd'])} {r['buy_cd_status']}")


if __name__ == "__main__":
    main()
