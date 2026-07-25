# -*- coding: utf-8 -*-
"""
日线长历史版（SPY 1993+）端到端验证：箱体→回抽级别L→TD级别=L×系数→低7-9抄底→P/R。

数据：SPY_adjusted.csv（日线）。级别 = 每 N 个交易日聚合：{1,2,3,4,5}。
跌幅门槛：{3%,5%,8%,10%}（日线尺度）。其余参数沿用盘中版。

自包含（复用 src 的 macd / td_sequential / czsc），不动盘中脚本。

用法：
  python scripts/run_daily_experiment.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.indicators.macd import calc_macd
from src.indicators.td_sequential import compute_td
from src.chan.czsc_vendor.analyze import CZSC
from src.chan.czsc_vendor.objects import RawBar
from src.chan.czsc_vendor.enum import Freq, Direction
from src.chan.czsc_vendor.utils.sig import get_zs_seq

DATA = REPO_ROOT / "data" / "SPY_adjusted.csv"
BOX_LEVELS = [1, 2, 3, 4, 5, 7, 10]   # 交易日（加密以增样本）
# 回抽闸放宽参数（路2）：放松"DIF 不超绿柱"与"DEA 触零"的容差
PULLBACK_GREEN_MULT = 1.15            # 允许 max(DIF) ≤ 1.15×最高绿柱
PULLBACK_DEA_TOL = 0.25               # DEA 触零相对容差（占 |DIF| 幅度）
COEFS = [2, 2.5, 3, 3.5, 4]
COUNTS = [7, 8, 9]
OCCS = [1, 2, 3]
NS = [1, 2, 3, 5, 8]
DROP_THRS = [0.03, 0.05, 0.08, 0.10]
MAX_BREAKDOWN_SCAN = 4
MIN_FIRED = 5

_DF_CACHE: dict[int, pd.DataFrame] = {}


def load_daily() -> pd.DataFrame:
    df = pd.read_csv(DATA, parse_dates=["时间"])
    return df[["时间", "开盘价", "最高价", "最低价", "收盘价", "成交量"]].reset_index(drop=True)


def day_df(base: pd.DataFrame, n: int) -> pd.DataFrame:
    """每 n 个交易日聚合 + 附 MACD/TD（缓存）。"""
    if n in _DF_CACHE:
        return _DF_CACHE[n]
    if n == 1:
        df = base.copy()
    else:
        g = base.groupby(base.index // n)
        df = pd.DataFrame({
            "时间": g["时间"].last().values,
            "开盘价": g["开盘价"].first().values,
            "最高价": g["最高价"].max().values,
            "最低价": g["最低价"].min().values,
            "收盘价": g["收盘价"].last().values,
            "成交量": g["成交量"].sum().values,
        })
    dif, dea, hist = calc_macd(df["收盘价"].tolist())
    df["DIF"], df["DEA"], df["HIST"] = dif, dea, hist
    td = compute_td(df["最高价"].tolist(), df["最低价"].tolist(), df["收盘价"].tolist())
    for k, v in td.items():
        df[k] = v
    _DF_CACHE[n] = df
    return df


def build_czsc(df: pd.DataFrame) -> CZSC:
    bars = [RawBar(symbol="SPY", id=i, dt=r["时间"].to_pydatetime(), freq=Freq.D,
                   open=float(r["开盘价"]), close=float(r["收盘价"]),
                   high=float(r["最高价"]), low=float(r["最低价"]),
                   vol=float(r["成交量"]), amount=0.0)
            for i, r in df.iterrows()]
    return CZSC(bars, max_bi_num=100000)


def detect_events(base, df, bi_list, zs_seq, level):
    """箱体→明显下跌 用例（含箱体低点→下跌前高点窗口、底部）。"""
    sdt_to_idx = {bi.sdt: i for i, bi in enumerate(bi_list)}
    events, seen = [], set()
    for zs in zs_seq:
        if len(zs.bis) < 3 or zs.zg <= zs.zd:
            continue
        box_h = zs.zg - zs.zd
        ci = sdt_to_idx.get(zs.bis[2].sdt)
        if ci is None:
            continue
        bk = None
        for j in range(ci, min(len(bi_list), ci + 1 + MAX_BREAKDOWN_SCAN)):
            bi = bi_list[j]
            if bi.direction == Direction.Down and bi.low < zs.zd and (bi.high - bi.low) >= box_h:
                bk = j
                break
        if bk is None or bk in seen:
            continue
        rally = next((bi_list[j] for j in range(bk - 1, -1, -1) if bi_list[j].direction == Direction.Up), None)
        if rally is None:
            continue
        seen.add(bk)
        bd = bi_list[bk]
        t_high = rally.fx_b.dt
        seg = df[(df["时间"] >= zs.sdt) & (df["时间"] <= t_high)]
        if seg.empty:
            continue
        t_low = seg.loc[seg["最低价"].idxmin(), "时间"]
        if t_low >= t_high:
            continue
        # 底部：在 1日 base 上，[高点, 跌破底分型+10交易日] 取最低
        bi_bottom = bd.fx_b.dt
        bpos = base.index[base["时间"] >= bi_bottom]
        endi = (bpos[0] + 10) if len(bpos) else len(base) - 1
        segb = base[(base["时间"] >= t_high) & (base.index <= endi)]
        if segb.empty:
            continue
        brow = segb.loc[segb["最低价"].idxmin()]
        events.append({
            "level": level, "box_zg": zs.zg, "box_zd": zs.zd,
            "rally_t0": t_low, "rally_t1": t_high,
            "rally_p1": rally.fx_b.fx,
            "bottom_t": brow["时间"], "bottom_p": float(brow["最低价"]),
        })
    return events


def pullback_levels(ev):
    """回抽零轴成立的日线级别 L 列表（三条件）。"""
    Ls = []
    for n in BOX_LEVELS:
        df = day_df(BASE, n)
        win = df[(df["时间"] >= ev["rally_t0"]) & (df["时间"] <= ev["rally_t1"])]
        if len(win) < 2:
            continue
        dif = win["DIF"].to_numpy(); hist = win["HIST"].to_numpy(); dea = win["DEA"].to_numpy()
        min_dif, max_dif = float(dif.min()), float(dif.max())
        green = hist[hist > 0]
        max_green = float(green.max()) if len(green) else None
        scale = max(abs(min_dif), abs(max_dif), 1e-9)
        a = min_dif < 0
        b = (max_dif > 0) and (max_green is not None) and (max_dif <= PULLBACK_GREEN_MULT * max_green)
        c = float(dea.max()) >= -PULLBACK_DEA_TOL * scale
        if a and b and c:
            Ls.append(n)
    return Ls


def td_level_days(L, coef):
    return max(1, int(round(L * coef)))


def signal_dist(ev, L, coef, count, occ):
    df = day_df(BASE, td_level_days(L, coef))
    th, tb = ev["rally_t1"], ev["bottom_t"]
    win = df[(df["时间"] >= th) & (df["时间"] <= tb + pd.Timedelta(days=20))]
    if len(win) < 2:
        return None, 0
    bottom_pos = win["最低价"].idxmin()
    sig = win[win["buy_setup"] == count]
    if len(sig) < occ:
        return None, len(win)
    return int(sig.index[occ - 1] - bottom_pos), len(win)


def metrics(rows, N):
    fired = hit = 0
    bsum = 0.0
    for dist, declen in rows:
        if declen >= 1:
            bsum += min(2 * N + 1, declen) / declen
        if dist is not None:
            fired += 1
            if abs(dist) <= N:
                hit += 1
    total = len(rows)
    prec = hit / fired if fired else 0.0
    base = bsum / total if total else 0.0
    return fired, prec, base, prec - base


def main():
    global BASE
    BASE = load_daily()
    print(f"SPY 日线: {len(BASE)} 根, {BASE['时间'].iloc[0].date()} ~ {BASE['时间'].iloc[-1].date()}")

    # 1) 扫箱体→下跌用例（各日线级别）
    events = []
    for n in BOX_LEVELS:
        df = day_df(BASE, n)
        c = build_czsc(df)
        evs = detect_events(BASE, df, c.bi_list, get_zs_seq(c.bi_list), n)
        events.extend(evs)
        print(f"  {n}日: 笔{len(c.bi_list)} 用例{len(evs)}")

    # 2) 附回抽级别 L → 样本(用例×L)
    samples = []
    for ev in events:
        for L in pullback_levels(ev):
            s = dict(ev); s["L"] = L
            s["drop"] = (ev["rally_p1"] - ev["bottom_p"]) / ev["rally_p1"]
            samples.append(s)
    print(f"下跌用例 {len(events)} → 含回抽级别样本 {len(samples)}")

    # 3) 预计算 dist
    dist_map = {}
    for i, s in enumerate(samples):
        for coef in COEFS:
            for count in COUNTS:
                for occ in OCCS:
                    dist_map[(i, coef, count, occ)] = signal_dist(s, s["L"], coef, count, occ)

    # 4) 网格 + 跌幅过滤 + 三拨 + 基准
    print("\n" + "=" * 96)
    print("  日线网格：跌幅过滤 × 系数 × 计数 × 第几次 × N | 三拨60/20/20 | lift=精度−随机基准")
    print("=" * 96)
    for thr in DROP_THRS:
        idxs = [i for i, s in enumerate(samples) if s["drop"] >= thr]
        idxs.sort(key=lambda i: samples[i]["rally_t1"])
        a, b = int(len(idxs) * 0.6), int(len(idxs) * 0.8)
        train, val, test = idxs[:a], idxs[a:b], idxs[b:]
        cfgs = []
        for coef in COEFS:
            for count in COUNTS:
                for occ in OCCS:
                    for N in NS:
                        rows = [dist_map[(i, coef, count, occ)] for i in train]
                        f, p, bl, lift = metrics(rows, N)
                        if f >= MIN_FIRED:
                            cfgs.append((coef, count, occ, N, lift))
        print(f"\n── 跌幅≥{thr*100:.0f}% 保留{len(idxs)} (训{len(train)}/验{len(val)}/测{len(test)}) 合格配置{len(cfgs)} ──")
        if not cfgs:
            print("    样本/触发不足")
            continue
        cfgs.sort(key=lambda c: c[4], reverse=True)
        top = cfgs[:10]
        def vlift(c):
            return metrics([dist_map[(i, c[0], c[1], c[2])] for i in val], c[3])[3]
        top.sort(key=vlift, reverse=True)
        coef, count, occ, N, trl = top[0]
        vf, vp, vb, vl = metrics([dist_map[(i, coef, count, occ)] for i in val], N)
        tf, tp, tb_, tl = metrics([dist_map[(i, coef, count, occ)] for i in test], N)
        print(f"    最优: 系数{coef} 低{count} 第{occ}次 N{N}")
        print(f"      训练 lift {trl:+.1%} | 验证 lift {vl:+.1%}(P{vp:.0%}/基准{vb:.0%}) | 测试 lift {tl:+.1%}(P{tp:.0%}/基准{tb_:.0%},触发{tf})")
    print("\n  注：daily 含 2008/2020/2022 大跌，样本与统计力远好于 60 天盘中版。")


if __name__ == "__main__":
    main()
