# -*- coding: utf-8 -*-
"""
阶段二：缠论自动扫"箱体（中枢）+ 明显下跌"，产出下跌用例样本。

每个用例输出：
  - level            : 箱体所在级别（分钟）
  - box_zg / box_zd  : 中枢上/下沿
  - rally_t0/p0      : 最后一波上拉的起涨低点（时间/价）
  - rally_t1/p1      : 局部高点（=下跌起点，时间/价）
  - breakdown_low    : 跌破笔的最低
  - bottom_t/bottom_p: 主跌浪底部（czsc 底分型 + 5m 精修）

"明显下跌"判据：中枢之后出现向下笔，最低 < 中枢下沿 zd，且该笔跌幅(high-low) ≥ 箱高(zg-zd)。
用户决策：**全部保留**（不去重，打级别标签）。

用法：
  # 可视化某级别某区间（人工校验检测是否正确）
  python scripts/scan_boxes.py --level 60 --start "2026-06-15" --end "2026-06-27" --viz
  # 批量扫全级别 → 样本表
  python scripts/scan_boxes.py --batch
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.chan.czsc_vendor.analyze import CZSC          # noqa: E402
from src.chan.czsc_vendor.objects import RawBar         # noqa: E402
from src.chan.czsc_vendor.enum import Freq, Direction   # noqa: E402
from src.chan.czsc_vendor.utils.sig import get_zs_seq   # noqa: E402

DATA_DIR = REPO_ROOT / "data" / "intraday"
BASE_MINUTES = 5
LEVELS = [5, 10, 15, 20, 30, 45, 60, 75, 90, 105, 120]
_FREQ = {5: Freq.F5, 10: Freq.F10, 15: Freq.F15, 20: Freq.F20, 30: Freq.F30,
         60: Freq.F60, 120: Freq.F120}  # 非标准级别用 F60 占位（仅标签，算法不依赖）

MAX_BREAKDOWN_SCAN = 4  # 中枢确立后，最多向后看几笔找跌破


@dataclass
class BoxEvent:
    level: int
    box_zg: float
    box_zd: float
    box_sdt: str
    box_edt: str
    rally_t0: str
    rally_p0: float
    rally_t1: str
    rally_p1: float
    breakdown_low: float
    bottom_t: str
    bottom_p: float


def _load_base() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / f"ESF_{BASE_MINUTES}m.csv", parse_dates=["时间"]).set_index("时间")


def _resample(base: pd.DataFrame, minutes: int) -> pd.DataFrame:
    if minutes == BASE_MINUTES:
        df = base.copy()
    else:
        df = base.resample(f"{minutes}min", label="left", closed="left").agg({
            "开盘价": "first", "最高价": "max", "最低价": "min",
            "收盘价": "last", "成交量": "sum",
        }).dropna(subset=["收盘价"])
    return df.reset_index()


def _build_czsc(df: pd.DataFrame, minutes: int) -> CZSC:
    freq = _FREQ.get(minutes, Freq.F60)
    bars = [RawBar(symbol="ES", id=i, dt=r["时间"].to_pydatetime(), freq=freq,
                   open=float(r["开盘价"]), close=float(r["收盘价"]),
                   high=float(r["最高价"]), low=float(r["最低价"]),
                   vol=float(r["成交量"]), amount=0.0)
            for i, r in df.iterrows()]
    return CZSC(bars, max_bi_num=100000)


def _refine_bottom(base: pd.DataFrame, t1, t_czsc) -> tuple:
    """在 5m 上 [局部高点, czsc底部+缓冲] 区间取真实最低点，精修底部。"""
    buf = pd.Timedelta(hours=12)
    seg = base[(base.index >= t1) & (base.index <= pd.Timestamp(t_czsc) + buf)]
    if seg.empty:
        return str(t_czsc), None
    row = seg.loc[seg["最低价"].idxmin()]
    return seg["最低价"].idxmin().strftime("%Y-%m-%d %H:%M:%S"), float(row["最低价"])


def detect_events(df: pd.DataFrame, bi_list, zs_seq, base: pd.DataFrame, level: int) -> list[BoxEvent]:
    sdt_to_idx = {bi.sdt: i for i, bi in enumerate(bi_list)}
    events: list[BoxEvent] = []
    seen_breakdown = set()
    for zs in zs_seq:
        if len(zs.bis) < 3 or zs.zg <= zs.zd:
            continue
        box_h = zs.zg - zs.zd
        core_idx = sdt_to_idx.get(zs.bis[2].sdt)
        if core_idx is None:
            continue
        # 中枢确立后向后找"跌破笔"
        bk = None
        for j in range(core_idx, min(len(bi_list), core_idx + 1 + MAX_BREAKDOWN_SCAN)):
            bi = bi_list[j]
            if bi.direction == Direction.Down and bi.low < zs.zd and (bi.high - bi.low) >= box_h:
                bk = j
                break
        if bk is None or bk in seen_breakdown:
            continue
        # 最后一波上拉 = 跌破笔前最近的向上笔
        rally = None
        for j in range(bk - 1, -1, -1):
            if bi_list[j].direction == Direction.Up:
                rally = bi_list[j]
                break
        if rally is None:
            continue
        seen_breakdown.add(bk)
        breakdown = bi_list[bk]
        # 上拉窗口口径：箱体低点 → 下跌前高点
        # 下跌前高点 = 最后一笔向上笔的顶；箱体低点 = [中枢起点, 高点] 内、箱体级别上的最低 low
        t_high = rally.fx_b.dt
        seg = df[(df["时间"] >= zs.sdt) & (df["时间"] <= t_high)]
        if seg.empty:
            continue
        low_row = seg.loc[seg["最低价"].idxmin()]
        t_low = low_row["时间"]
        if t_low >= t_high:
            continue
        bt, bp = _refine_bottom(base, t_high, breakdown.fx_b.dt)
        events.append(BoxEvent(
            level=level, box_zg=round(zs.zg, 2), box_zd=round(zs.zd, 2),
            box_sdt=zs.sdt.strftime("%Y-%m-%d %H:%M:%S"), box_edt=zs.edt.strftime("%Y-%m-%d %H:%M:%S"),
            rally_t0=t_low.strftime("%Y-%m-%d %H:%M:%S"), rally_p0=round(float(low_row["最低价"]), 2),
            rally_t1=t_high.strftime("%Y-%m-%d %H:%M:%S"), rally_p1=round(rally.fx_b.fx, 2),
            breakdown_low=round(breakdown.low, 2),
            bottom_t=bt, bottom_p=bp,
        ))
    return events


def _viz(df, bi_list, zs_seq, events, level, start, end, out_dir):
    # 按 K 线序号排列（折叠休市空档，和 TradingView 一致），不用真实时间轴
    view = df[(df["时间"] >= start) & (df["时间"] <= end)].reset_index(drop=True)
    n = len(view)
    if n == 0:
        return None
    ts = view["时间"].to_numpy()

    def pos(t):
        i = int(np.searchsorted(ts, np.datetime64(pd.Timestamp(t))))
        return min(max(i, 0), n - 1)

    fig, ax = plt.subplots(figsize=(14, 7))
    for i, r in view.iterrows():
        c = "#26a69a" if r["收盘价"] >= r["开盘价"] else "#ef5350"
        ax.plot([i, i], [r["最低价"], r["最高价"]], color=c, lw=0.9, zorder=1)
        ax.plot([i, i], [r["开盘价"], r["收盘价"]], color=c, lw=2.4, zorder=1)
    # 笔（fx 折线）
    if bi_list:
        raw = [(bi_list[0].fx_a.dt, bi_list[0].fx_a.fx)] + [(b.fx_b.dt, b.fx_b.fx) for b in bi_list]
        pts = [(pos(t), v) for t, v in raw if start <= pd.Timestamp(t) <= end]
        if pts:
            ax.plot([p[0] for p in pts], [p[1] for p in pts], color="#444", lw=1.0, zorder=2)
    # 中枢（矩形）
    for zs in zs_seq:
        if zs.edt < start or zs.sdt > end:
            continue
        x0, x1 = pos(zs.sdt), pos(zs.edt)
        ax.add_patch(Rectangle((x0, zs.zd), max(x1 - x0, 0.5), zs.zg - zs.zd,
                               facecolor="#9b59b6", alpha=0.12, edgecolor="#9b59b6", lw=1, zorder=0))
    # 事件：上拉窗口高亮 + 局部高点 + 底部
    for e in events:
        t0, t1 = pd.Timestamp(e.rally_t0), pd.Timestamp(e.rally_t1)
        if t1 < start or t0 > end:
            continue
        ax.axvspan(pos(t0), pos(t1), color="#f1c40f", alpha=0.18, zorder=0)
        ax.scatter([pos(t1)], [e.rally_p1], color="red", marker="v", s=70, zorder=5)
        if e.bottom_p is not None:
            ax.scatter([pos(e.bottom_t)], [e.bottom_p], color="blue", marker="^", s=70, zorder=5)

    k = max(1, n // 8)
    ticks = list(range(0, n, k))
    ax.set_xticks(ticks)
    ax.set_xticklabels([pd.Timestamp(ts[i]).strftime("%m-%d\n%H:%M") for i in ticks])
    ax.set_title(f"ES=F {level}m  czsc box/drop detection  {start:%m-%d} ~ {end:%m-%d}\n"
                 f"purple=ZS(box)  gray=bi  yellow=last rally  red v=drop start  blue ^=bottom")
    ax.set_ylabel("Price")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"boxscan_{level}m.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def main():
    parser = argparse.ArgumentParser(description="阶段二：缠论扫箱体+下跌")
    parser.add_argument("--level", type=int, default=60)
    parser.add_argument("--start", default="2026-04-17")
    parser.add_argument("--end", default="2026-06-28")
    parser.add_argument("--viz", action="store_true", help="出可视化校验图")
    parser.add_argument("--batch", action="store_true", help="批量扫全级别产样本表")
    parser.add_argument("--out-dir", type=Path, default=DATA_DIR / "box_charts")
    args = parser.parse_args()

    base = _load_base()

    if args.batch:
        all_events: list[BoxEvent] = []
        for lv in LEVELS:
            df = _resample(base, lv)
            c = _build_czsc(df, lv)
            zs = get_zs_seq(c.bi_list)
            evs = detect_events(df, c.bi_list, zs, base, lv)
            all_events.extend(evs)
            print(f"  {lv:>3}m: 笔 {len(c.bi_list):>4}  中枢 {len(zs):>3}  下跌用例 {len(evs)}")
        out = DATA_DIR / "box_events.json"
        out.write_text(json.dumps([asdict(e) for e in all_events], ensure_ascii=False, indent=2))
        print(f"\n共 {len(all_events)} 个用例 -> {out}")
        return

    # 单级别可视化
    start, end = pd.Timestamp(args.start), pd.Timestamp(args.end)
    df = _resample(base, args.level)
    c = _build_czsc(df, args.level)
    zs = get_zs_seq(c.bi_list)
    events = detect_events(df, c.bi_list, zs, base, args.level)
    in_range = [e for e in events if start <= pd.Timestamp(e.rally_t1) <= end]
    print(f"{args.level}m  笔 {len(c.bi_list)}  中枢 {len(zs)}  下跌用例(总) {len(events)}  区间内 {len(in_range)}")
    for e in in_range:
        print(f"  箱体[{e.box_zd}~{e.box_zg}] 上拉 {e.rally_t0}->{e.rally_t1}({e.rally_p1}) "
              f"底 {e.bottom_t}({e.bottom_p})")
    if args.viz:
        path = _viz(df, c.bi_list, zs, events, args.level, start, end, args.out_dir)
        print(f"图已保存 {path}")


if __name__ == "__main__":
    main()
