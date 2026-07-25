# -*- coding: utf-8 -*-
"""
多级别 MACD 回抽零轴扫描（MACD 回抽零轴任务·阶段一第二步）

输入：一个"最后上拉时间窗口" [起涨低点, 局部高点]（北京时间）。
处理：对 {5,10,15,20,30,60,120} 分钟七个级别，各算 MACD（12/26/9，hist=DIF−DEA），
      在窗口内判定"回抽零轴"三条件：
        (a) min(DIF) < 0                      # 先沉到零轴下
        (b) 0 < max(DIF) ≤ max(绿柱)          # 回抽到零轴上但不超最高绿柱（DIF 峰与绿柱顶可不同根）
        (c) DEA 触及/略穿零轴                   # DEA 峰值抬升到零轴附近容差带
输出：按级别从小到大的结果表（含原始数值），以及每个级别一张图（价格 + MACD，高亮窗口）。

注：MACD 在每个级别上用"全历史"计算以保证 EMA 充分预热，仅在窗口内读数判定。
    条件 (c) 的容差为相对值（占窗口内 |DIF| 幅度的比例），默认偏宽松，供出图后校准。

用法：
    python scripts/scan_macd_zero_pullback.py \
        --start "2026-06-22 07:00" --end "2026-06-22 22:00"
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

from src.indicators.macd import calc_macd  # noqa: E402

# 默认级别集合（分钟）：在 30~120 区间加密，覆盖 90m 等"网格缝隙"
LEVELS = [5, 10, 15, 20, 30, 45, 60, 75, 90, 105, 120]
DATA_DIR = REPO_ROOT / "data" / "intraday"
BASE_MINUTES = 5


def _load_base(prefix: str) -> pd.DataFrame:
    """读取 5 分钟基础数据，作为任意级别重采样的源。"""
    path = DATA_DIR / f"{prefix}_{BASE_MINUTES}m.csv"
    return pd.read_csv(path, parse_dates=["时间"]).set_index("时间")


def _resample(base: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """从 5m 基础数据现场重采样到 minutes 级别，并附 MACD（全历史预热）。"""
    if minutes == BASE_MINUTES:
        df = base.copy()
    else:
        df = base.resample(f"{minutes}min", label="left", closed="left").agg({
            "开盘价": "first", "最高价": "max", "最低价": "min",
            "收盘价": "last", "成交量": "sum",
        }).dropna(subset=["收盘价"])
    df = df.reset_index()
    closes = df["收盘价"].tolist()
    dif, dea, hist = calc_macd(closes)
    df["DIF"], df["DEA"], df["HIST"] = dif, dea, hist
    return df


def _scan_level(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp,
                dea_tol_frac: float) -> dict:
    """在窗口内判定三条件，返回度量与判定结果。"""
    mask = (df["时间"] >= start) & (df["时间"] <= end)
    win = df[mask]
    res = {"bars": len(win), "ok": False, "skip": False}
    if len(win) < 2:
        res["skip"] = True
        res["reason"] = "窗口内 K 线不足"
        return res

    dif = win["DIF"].to_numpy()
    hist = win["HIST"].to_numpy()
    dea = win["DEA"].to_numpy()

    min_dif = float(dif.min())
    max_dif = float(dif.max())
    green = hist[hist > 0]
    max_green = float(green.max()) if len(green) else None
    dea_peak = float(dea.max())

    # 相对容差：以窗口内 |DIF| 幅度为尺度
    scale = max(abs(min_dif), abs(max_dif), 1e-9)
    dea_tol_abs = dea_tol_frac * scale

    cond_a = min_dif < 0
    cond_b = (max_dif > 0) and (max_green is not None) and (max_dif <= max_green)
    cond_c = dea_peak >= -dea_tol_abs  # DEA 抬升到零轴附近/上方

    res.update({
        "min_dif": min_dif, "max_dif": max_dif, "max_green": max_green,
        "dea_peak": dea_peak, "dea_tol_abs": dea_tol_abs,
        "a": cond_a, "b": cond_b, "c": cond_c,
        "ok": cond_a and cond_b and cond_c,
    })
    return res


def _plot_level(df: pd.DataFrame, minutes: int, start: pd.Timestamp, end: pd.Timestamp,
                res: dict, out_dir: Path) -> Path:
    """画价格 + MACD 两栏图，高亮窗口，标注 DIF 峰与最高绿柱。"""
    # 取窗口前后一些上下文
    span = end - start
    pad = span * 0.4
    lo, hi = start - pad, end + pad
    view = df[(df["时间"] >= lo) & (df["时间"] <= hi)].copy()
    if view.empty:
        view = df[(df["时间"] >= start) & (df["时间"] <= end)].copy()

    t = view["时间"]
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), sharex=True,
                                   gridspec_kw={"height_ratios": [2, 1]})

    ax1.plot(t, view["收盘价"], color="#333", lw=1.0)
    ax1.set_title(f"ES=F {minutes}m  |  window {start:%m-%d %H:%M} ~ {end:%m-%d %H:%M} (Beijing)  "
                  f"|  {'PASS' if res.get('ok') else ('SKIP' if res.get('skip') else 'FAIL')}")
    ax1.set_ylabel("Price")
    ax1.axvspan(start, end, color="#9b59b6", alpha=0.12)
    ax1.grid(alpha=0.25)

    # MACD 栏
    colors = ["#26a69a" if h >= 0 else "#ef5350" for h in view["HIST"]]
    width = (span.total_seconds() / max(len(view), 1)) / 86400.0 * 0.7
    ax2.bar(t, view["HIST"], width=width, color=colors, align="center")
    ax2.plot(t, view["DIF"], color="#2962ff", lw=1.1, label="DIF")
    ax2.plot(t, view["DEA"], color="#ff6d00", lw=1.1, label="DEA")
    ax2.axhline(0, color="#787b86", lw=0.8)
    ax2.axvspan(start, end, color="#9b59b6", alpha=0.12)
    ax2.set_ylabel("MACD")
    ax2.legend(loc="upper left", fontsize=8)
    ax2.grid(alpha=0.25)

    # 标注窗口内 DIF 峰值
    if not res.get("skip"):
        win = df[(df["时间"] >= start) & (df["时间"] <= end)]
        i_max = win["DIF"].idxmax()
        ax2.scatter([df.loc[i_max, "时间"]], [df.loc[i_max, "DIF"]],
                    color="#2962ff", zorder=5, s=30)
        ax2.annotate(f"max(DIF)={res['max_dif']:.2f}",
                     (df.loc[i_max, "时间"], df.loc[i_max, "DIF"]),
                     fontsize=8, color="#2962ff",
                     xytext=(5, 6), textcoords="offset points")
        txt = (f"min(DIF)={res['min_dif']:.2f}  max(green)="
               f"{res['max_green']:.2f}" if res['max_green'] is not None else
               f"min(DIF)={res['min_dif']:.2f}  max(green)=None")
        txt += f"  DEA_peak={res['dea_peak']:.2f}"
        ax2.text(0.01, 0.02, f"(a){'Y' if res['a'] else 'N'} (b){'Y' if res['b'] else 'N'} "
                 f"(c){'Y' if res['c'] else 'N'}  |  {txt}",
                 transform=ax2.transAxes, fontsize=8,
                 bbox=dict(boxstyle="round", fc="white", ec="#ccc", alpha=0.8))

    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d\n%H:%M"))
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"macd_{minutes}m.png"
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def main():
    parser = argparse.ArgumentParser(description="多级别 MACD 回抽零轴扫描")
    parser.add_argument("--start", required=True, help="起涨低点时间（北京时间，如 '2026-06-22 07:00'）")
    parser.add_argument("--end", required=True, help="局部高点时间（北京时间）")
    parser.add_argument("--prefix", default="ESF", help="数据文件前缀，默认 ESF")
    parser.add_argument("--levels", type=str, default=None,
                        help="自定义级别集合（分钟，逗号分隔，须为 5 的整数倍），默认见 LEVELS")
    parser.add_argument("--dea-tol-frac", type=float, default=0.10,
                        help="条件(c) DEA 触零的相对容差（占窗口|DIF|幅度比例），默认 0.10")
    parser.add_argument("--out-dir", type=Path,
                        default=DATA_DIR / "scan_charts", help="图表输出目录")
    args = parser.parse_args()

    levels = [int(x) for x in args.levels.split(",")] if args.levels else LEVELS

    start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end)

    print("=" * 78)
    print(f"  多级别 MACD 回抽零轴扫描  |  窗口(北京时间) {start} ~ {end}")
    print(f"  三条件: (a) min(DIF)<0   (b) 0<max(DIF)≤max(绿柱)   (c) DEA 触/略穿零轴")
    print("=" * 78)
    header = f"{'级别':>5} {'根数':>4} {'(a)':>4} {'(b)':>4} {'(c)':>4} {'判定':>6} " \
             f"{'min(DIF)':>10} {'max(DIF)':>10} {'max(绿柱)':>10} {'DEA峰':>9}"
    print(header)
    print("-" * 78)

    base = _load_base(args.prefix)
    passed = []
    for minutes in levels:
        df = _resample(base, minutes)
        res = _scan_level(df, start, end, args.dea_tol_frac)
        _plot_level(df, minutes, start, end, res, args.out_dir)

        if res.get("skip"):
            print(f"{minutes:>4}m {res['bars']:>4}  ——   ——   ——   {'跳过':>6}  ({res.get('reason','')})")
            continue

        def fmt(x):
            return f"{x:>10.2f}" if x is not None else f"{'None':>10}"
        verdict = "命中" if res["ok"] else "未命中"
        if res["ok"]:
            passed.append(minutes)
        print(f"{minutes:>4}m {res['bars']:>4} "
              f"{('Y' if res['a'] else 'N'):>4} {('Y' if res['b'] else 'N'):>4} "
              f"{('Y' if res['c'] else 'N'):>4} {verdict:>6} "
              f"{fmt(res['min_dif'])} {fmt(res['max_dif'])} {fmt(res['max_green'])} "
              f"{res['dea_peak']:>9.2f}")

    print("-" * 78)
    print(f"  命中级别（从小到大）: {passed if passed else '无'}")
    print(f"  图表输出: {args.out_dir}")
    print("=" * 78)


if __name__ == "__main__":
    main()
