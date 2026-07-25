# -*- coding: utf-8 -*-
"""
czsc 缠论买卖点 → 机器学习特征（可复用指标模块）

对外提供 `compute_czsc_bsp(spy_df)`，为**每个交易日**产出一组缠论衍生特征列。

核心约束（详见 docs/tasks/260628-czsc-chart-and-ml-features）：
  - **纯实时因果口径**：每个交易日的特征只用「截至当日」的逐根增量缠论状态，
    绝不使用全量最终结构（否则偷看未来 / look-ahead）。
  - 买卖点取**实时触发**（含此后会被重绘的信号，不事后剔除）——重绘与否是未来信息，
    剔除即作弊；模型的职责正是从中过滤噪声（meta-labeling）。

输出 5 列连续/类别特征：
  czsc_days_since_rt_buy  距上一个实时买点的交易日数（首个买点前填 999）
  czsc_last_buy_type      上个实时买点类别（1/2/3；无则 0）
  czsc_beichi_strength    最近下跌笔相对前一下跌笔的力度比（价差/量能/长度均值；<1=背驰，越小越衰竭）
  czsc_in_zs              当日收盘是否落在「截至当日已成立」的中枢内（0/1）
  czsc_zs_pos             当日收盘在该中枢内相对位置 (close-zd)/(zg-zd)（无中枢填 0.5）
"""
import numpy as np
import pandas as pd

from src.chan.czsc_vendor import CZSC, RawBar, Freq, Mark, Direction
from src.chan.czsc_vendor.utils.sig import get_zs_seq
from src.chan.czsc_vendor.utils.tas import update_ma_cache
from src.chan.czsc_vendor.signals_cxt import (
    cxt_first_buy_V221126,    # 一买
    cxt_first_sell_V221126,   # 一卖
    cxt_second_bs_V230320,    # 二买 / 二卖（SMA21）
    cxt_third_buy_V230228,    # 三买（纯笔）
    cxt_third_bs_V230319,     # 三买 / 三卖（SMA34）
)

_BSP_FUNCS = [
    cxt_first_buy_V221126,
    cxt_first_sell_V221126,
    cxt_second_bs_V230320,
    cxt_third_buy_V230228,
    cxt_third_bs_V230319,
]

CZSC_FEATURE_COLS = [
    "czsc_days_since_rt_buy",
    "czsc_last_buy_type",
    "czsc_beichi_strength",
    "czsc_in_zs",
    "czsc_zs_pos",
]

_DAYS_SINCE_CAP = 999.0
_NEUTRAL_BEICHI = 1.0
_NEUTRAL_ZS_POS = 0.5


def _buy_type_code(v1: str) -> int:
    """买点类别 → 1/2/3；非买点返回 0。"""
    if "买" not in v1:
        return 0
    if "一" in v1:
        return 1
    if "二" in v1:
        return 2
    if "三" in v1:
        return 3
    return 0


def _to_raw_bars(spy_df: pd.DataFrame):
    bars = []
    for i, row in enumerate(spy_df.itertuples(index=False)):
        vol = float(getattr(row, "volume", 0) or 0)
        close = float(row.close)
        bars.append(RawBar(
            symbol="SPY", id=i,
            dt=pd.Timestamp(row.date).to_pydatetime(),
            freq=Freq.D,
            open=float(row.open), high=float(row.high),
            low=float(row.low), close=close,
            vol=vol, amount=vol * close,
        ))
    return bars


def _ratio(a, b):
    return (a / b) if b else 1.0


def compute_czsc_bsp(spy_df: pd.DataFrame):
    """为 spy_df 的每个交易日计算 czsc 因果特征。

    Args:
        spy_df: 含 [date, open, high, low, close, volume]，按日期升序。
    Returns:
        (DataFrame[date + CZSC_FEATURE_COLS], CZSC_FEATURE_COLS)
    """
    n = len(spy_df)
    days_since = np.full(n, _DAYS_SINCE_CAP)
    last_type = np.zeros(n)
    beichi = np.full(n, _NEUTRAL_BEICHI)
    in_zs = np.zeros(n)
    zs_pos = np.full(n, _NEUTRAL_ZS_POS)

    if n < 30:
        out = pd.DataFrame({"date": spy_df["date"].values})
        for c in CZSC_FEATURE_COLS:
            out[c] = (_DAYS_SINCE_CAP if c == "czsc_days_since_rt_buy"
                      else _NEUTRAL_BEICHI if c == "czsc_beichi_strength"
                      else _NEUTRAL_ZS_POS if c == "czsc_zs_pos" else 0.0)
        out["czsc_buy_today"] = 0.0
        return out, CZSC_FEATURE_COLS

    buy_today = np.zeros(n)  # 当日恰好触发任意类买点 = 1（精确日口径，较稀疏）

    bars = _to_raw_bars(spy_df)
    big = len(bars)

    # 均线缓存预填：SMA21/34 为「因果」滚动均值（仅用过去），二/三类买卖点信号需要它。
    # 在共享的 RawBar 对象上预填后，逐根回放时 update_ma_cache 直接早返回，避免 O(n^2)。
    c_full = CZSC(bars, max_bi_num=big)
    update_ma_cache(c_full, ma_type="SMA", timeperiod=21)
    update_ma_cache(c_full, ma_type="SMA", timeperiod=34)

    # 逐根增量回放：对每个交易日快照「截至当日」的缠论状态
    c = CZSC(bars[:1], max_bi_num=big)
    last_fire_idx = None
    last_fire_type = 0
    last_state = None

    for i in range(1, n):
        c.update(bars[i])
        L = len(c.bi_list)

        # ── 背驰强度：最近下跌笔 vs 前一下跌笔（价差/量能/长度均值比）──
        if L >= 2:
            downs = [b for b in c.bi_list if b.direction == Direction.Down]
            if len(downs) >= 2:
                last_d, prev_d = downs[-1], downs[-2]
                r_price = _ratio(last_d.power_price, prev_d.power_price)
                r_len = _ratio(last_d.length, prev_d.length)
                if prev_d.power_volume:
                    r_vol = _ratio(last_d.power_volume, prev_d.power_volume)
                    val = float(np.mean([r_price, r_vol, r_len]))
                else:
                    val = float(np.mean([r_price, r_len]))
                beichi[i] = float(np.clip(val, 0.0, 5.0))  # 截断极端比值，<1=背驰
            else:
                beichi[i] = beichi[i - 1]

            # ── 中枢：取截至当日的最近一个有效中枢，判位置 ──
            zs_seq = get_zs_seq(c.bi_list)
            if zs_seq:
                zs = zs_seq[-1]
                if len(zs.bis) >= 3 and zs.zg >= zs.zd:
                    cl = bars[i].close
                    in_zs[i] = 1.0 if (zs.zd <= cl <= zs.zg) else 0.0
                    rng = zs.zg - zs.zd
                    pos = (cl - zs.zd) / rng if rng > 0 else _NEUTRAL_ZS_POS
                    zs_pos[i] = float(np.clip(pos, -2.0, 3.0))  # 截断远离陈旧中枢的极端值
        else:
            beichi[i] = beichi[i - 1]

        # ── 实时买点：最后一笔变化时评估 di=1（含此后会被重绘的信号）──
        if L >= 7:
            anchor = c.bi_list[-1]
            state = (L, anchor.fx_b.dt)
            if state != last_state:
                last_state = state
                for fn in _BSP_FUNCS:
                    try:
                        sig = fn(c, di=1)
                    except Exception:
                        continue
                    for v in sig.values():
                        v1 = v.split("_")[0]
                        code = _buy_type_code(v1)
                        if code:  # 只记录买点
                            last_fire_idx = i
                            last_fire_type = code
                            buy_today[i] = 1.0

        if last_fire_idx is not None:
            days_since[i] = float(i - last_fire_idx)
            last_type[i] = last_fire_type

    out = pd.DataFrame({
        "date": spy_df["date"].values,
        "czsc_days_since_rt_buy": days_since,
        "czsc_last_buy_type": last_type,
        "czsc_beichi_strength": beichi,
        "czsc_in_zs": in_zs,
        "czsc_zs_pos": zs_pos,
        "czsc_buy_today": buy_today,  # 额外列（不在 CZSC_FEATURE_COLS 内，供单布尔实验用）
    })
    return out, CZSC_FEATURE_COLS
