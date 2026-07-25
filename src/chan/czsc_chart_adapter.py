# -*- coding: utf-8 -*-
"""
czsc 缠论 → 交互式图表 适配层

把 K 线数据喂入 vendored czsc 核心，提取：
  - 分型 FX（笔端点）/ 笔 BI / 中枢 ZS（结构，三视图共用）
  - 一二三类买卖点，并按"看到的时点"区分三种视图：
      * hindsight（事后复盘）：最终结构上的真实买卖点，标在拐点极值 —— 有前视偏差
      * realtime（实时回放）：历史上实时真正触发过的全部信号，标在首次出现日，
                              并区分"后来幸存(survived)"与"后来被结构推翻(repainted)"
      * confirmed（确认实战）：被 czsc finished_bis 确认、不再重绘的信号，标在确认日 —— 可实战

输出为可直接 json.dumps 的纯 dict / list，供 interactive_chart 渲染。
"""
from datetime import datetime

from src.chan.czsc_vendor import CZSC, RawBar, Freq, Mark
from src.chan.czsc_vendor.utils.sig import get_zs_seq
from src.chan.czsc_vendor.utils.tas import update_ma_cache
from src.chan.czsc_vendor.signals_cxt import (
    cxt_first_buy_V221126,    # 一买
    cxt_first_sell_V221126,   # 一卖
    cxt_second_bs_V230320,    # 二买 / 二卖（SMA21 辅助）
    cxt_third_buy_V230228,    # 三买（纯笔）
    cxt_third_bs_V230319,     # 三买 / 三卖（SMA34 辅助）
)

# 一二三类买卖点信号函数集合（spike_czsc.py 验证过、能在 SPY 历史真实触发）
_BSP_FUNCS = [
    cxt_first_buy_V221126,
    cxt_first_sell_V221126,
    cxt_second_bs_V230320,
    cxt_third_buy_V230228,
    cxt_third_bs_V230319,
]

_BUY_KEYWORD = '买'
_SELL_KEYWORD = '卖'

# 标记样式
_C_BUY = '#26a69a'
_C_SELL = '#ef5350'
_C_REPAINT = '#787b86'   # 被重绘抹掉的失败信号：灰色


def _to_raw_bars(data, symbol='SPY'):
    """把 [{date, open, high, low, close}, ...] 转成 czsc 的 RawBar 列表。"""
    bars = []
    for i, d in enumerate(data):
        vol = float(d.get('volume', 0) or 0)
        bars.append(RawBar(
            symbol=symbol, id=i,
            dt=datetime.strptime(d['date'], '%Y-%m-%d'),
            freq=Freq.D,
            open=float(d['open']), high=float(d['high']),
            low=float(d['low']), close=float(d['close']),
            vol=vol, amount=vol * float(d['close']),
        ))
    return bars


def _side_of(v1):
    """信号 v1 文本 → 'buy' / 'sell' / None。"""
    if _BUY_KEYWORD in v1:
        return 'buy'
    if _SELL_KEYWORD in v1:
        return 'sell'
    return None


def _scan_signals(c, di):
    """在 CZSC 对象上以倒数第 di 个笔为锚点扫描买卖点，返回 [(v1, side), ...]。"""
    hits = []
    for fn in _BSP_FUNCS:
        try:
            sig = fn(c, di=di)
        except Exception:
            continue
        for v in sig.values():
            v1 = v.split('_')[0]
            if v1 in ('其他', '任意'):
                continue
            side = _side_of(v1)
            if side:
                hits.append((v1, side))
    return hits


def _signal_marker(time, v1, side):
    """幸存/确认买卖点：彩色箭头。带 side / ctype 供图层过滤。"""
    if side == 'buy':
        return {'time': time, 'position': 'belowBar', 'shape': 'arrowUp',
                'color': _C_BUY, 'text': v1, 'side': 'buy', 'ctype': v1}
    return {'time': time, 'position': 'aboveBar', 'shape': 'arrowDown',
            'color': _C_SELL, 'text': v1, 'side': 'sell', 'ctype': v1}


def _repaint_marker(time, side, ctype):
    """被重绘抹掉的失败信号：灰色「带方向」箭头 + ✗，一眼看出原本是买还是卖。"""
    if side == 'buy':
        return {'time': time, 'position': 'belowBar', 'shape': 'arrowUp',
                'color': _C_REPAINT, 'text': '✗', 'side': 'buy', 'ctype': ctype}
    return {'time': time, 'position': 'aboveBar', 'shape': 'arrowDown',
            'color': _C_REPAINT, 'text': '✗', 'side': 'sell', 'ctype': ctype}


def build_czsc_overlay(data, symbol='SPY'):
    """构建 czsc 叠加层数据（含三视图买卖点 + 悬停明细）。

    Returns dict:
        fractals / bi / zs           —— 结构，三视图共用
        marker_sets.{hindsight,realtime,confirmed} —— 三视图各自的买卖点标记
        detail_map                   —— {date: html}，鼠标悬停明细
        counts                       —— 各视图统计
        confirm_lag_median           —— 确认过滤的入场延迟中位数（交易日）
    数据不足时返回 None。
    """
    bars = _to_raw_bars(data, symbol)
    if len(bars) < 30:
        return None
    big = len(bars)

    # ── 1) 全量结构 + 均线缓存预填（让后续逐根回放时均线早返回、避免 O(n^2)）──
    c = CZSC(bars, max_bi_num=big)
    update_ma_cache(c, ma_type='SMA', timeperiod=21)
    update_ma_cache(c, ma_type='SMA', timeperiod=34)
    n = len(c.bi_list)

    # ── 2) confirmed（最终结构上的真实买卖点）：按 di 扫描已确认笔 ──
    # key=(extreme_date, v1) -> {'side', 'extreme'}
    confirmed = {}
    for di in range(1, n + 1):
        anchor = c.bi_list[-di]
        ed = anchor.fx_b.dt.strftime('%Y-%m-%d')
        for v1, side in _scan_signals(c, di):
            confirmed.setdefault((ed, v1), {'side': side, 'extreme': ed})

    # ── 3) 逐根增量回放：实时首次触发 + 每个笔的确认日（finished_bis）──
    rc = CZSC(bars[:1], max_bi_num=big)
    finish_date = {}        # fx_b 日期 -> 该笔进入 finished_bis 的确认日
    realtime = {}           # (extreme_date, v1) -> {'fire_date', 'side'}
    last_state = None
    for i in range(1, len(bars)):
        rc.update(bars[i])
        cur = bars[i].dt.strftime('%Y-%m-%d')

        # 新确认的笔（从尾部往前，遇到已记录即停 —— 摊还 O(1)）
        for bi in reversed(rc.finished_bis):
            d = bi.fx_b.dt.strftime('%Y-%m-%d')
            if d in finish_date:
                break
            finish_date[d] = cur

        # 实时信号：仅在"最后一笔"变化时评估 di=1（含笔延伸导致 fx_b 移动）
        L = len(rc.bi_list)
        if L >= 7:
            anchor = rc.bi_list[-1]
            state = (L, anchor.fx_b.dt)
            if state != last_state:
                last_state = state
                ad = anchor.fx_b.dt.strftime('%Y-%m-%d')
                for v1, side in _scan_signals(rc, di=1):
                    realtime.setdefault((ad, v1), {'fire_date': cur, 'side': side})

    # ── 4) 组装三视图标记 + 悬停明细 ──
    detail = {}  # date -> [str, ...]

    def _add_detail(date, text):
        detail.setdefault(date, [])
        if text not in detail[date]:
            detail[date].append(text)

    # hindsight：真实信号标在极值
    hindsight_markers = []
    confirmed_markers = []
    lags = []
    idx_of = {d['date']: i for i, d in enumerate(data)}
    for (ed, v1), info in confirmed.items():
        side = info['side']
        hindsight_markers.append(_signal_marker(ed, v1, side))
        _add_detail(ed, f'{v1} · 拐点(事后视角)')

        cdate = finish_date.get(ed, ed)
        confirmed_markers.append(_signal_marker(cdate, v1, side))
        _add_detail(cdate, f'{v1} · 确认信号(可实战，极值 {ed})')
        if ed in idx_of and cdate in idx_of:
            lags.append(idx_of[cdate] - idx_of[ed])

    # realtime：实时触发全集，区分幸存/被重绘
    realtime_markers = []
    n_survived = n_repaint = 0
    for (ed, v1), info in realtime.items():
        side = info['side']
        fdate = info['fire_date']
        survived = (ed, v1) in confirmed
        if survived:
            n_survived += 1
            realtime_markers.append(_signal_marker(fdate, v1, side))
            _add_detail(fdate, f'{v1} · 实时触发 · ✓后确认')
        else:
            n_repaint += 1
            realtime_markers.append(_repaint_marker(fdate, side, v1))
            _add_detail(fdate, f'{v1} · 实时触发 · ✗后被推翻(重绘消失)')

    detail_map = {d: '<br>'.join(items) for d, items in detail.items()}

    # ── 5) 结构：分型(笔端点) / 笔 / 中枢 ──
    fractals = []
    if c.bi_list:
        first = c.bi_list[0]
        fractals.append({'time': first.fx_a.dt.strftime('%Y-%m-%d'),
                         'value': round(first.fx_a.fx, 4),
                         'mark': 'G' if first.fx_a.mark == Mark.G else 'D'})
        for bi in c.bi_list:
            fractals.append({'time': bi.fx_b.dt.strftime('%Y-%m-%d'),
                             'value': round(bi.fx_b.fx, 4),
                             'mark': 'G' if bi.fx_b.mark == Mark.G else 'D'})
    bi_points = [{'time': f['time'], 'value': f['value']} for f in fractals]

    zs_boxes = []
    for zs in get_zs_seq(c.bi_list):
        if len(zs.bis) < 3 or zs.zg < zs.zd:
            continue
        zs_boxes.append({'sdt': zs.sdt.strftime('%Y-%m-%d'),
                         'edt': zs.edt.strftime('%Y-%m-%d'),
                         'zg': round(zs.zg, 4), 'zd': round(zs.zd, 4),
                         'zz': round(zs.zz, 4)})

    n_conf_buy = sum(1 for v in confirmed.values() if v['side'] == 'buy')
    n_conf_sell = sum(1 for v in confirmed.values() if v['side'] == 'sell')
    lags.sort()
    lag_median = lags[len(lags) // 2] if lags else 0

    return {
        'fractals': fractals,
        'bi': bi_points,
        'zs': zs_boxes,
        'marker_sets': {
            'hindsight': sorted(hindsight_markers, key=lambda m: m['time']),
            'realtime': sorted(realtime_markers, key=lambda m: m['time']),
            'confirmed': sorted(confirmed_markers, key=lambda m: m['time']),
        },
        'detail_map': detail_map,
        'counts': {
            'hindsight': {'buy': n_conf_buy, 'sell': n_conf_sell},
            'confirmed': {'buy': n_conf_buy, 'sell': n_conf_sell},
            'realtime': {'survived': n_survived, 'repaint': n_repaint},
        },
        'confirm_lag_median': lag_median,
    }
