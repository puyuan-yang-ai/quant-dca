"""
RSI v2 信号计算模块

翻译自 PineScript most-on-rsi-v2.pine 的三事件信号系统：
  事件1: RSI 下破/上破极端阈值 → B/S（左侧预警）
  事件2: RSI 上穿/下穿快均线 + 门槛 → B/B+/B++（右侧确认）
  事件3: 实时背离检测 → B+/S+，近期有交叉可升级 B++/S++

仅用于可视化展示，不接入策略决策流程。
"""

from src.indicators import calc_rsi, calc_ema


def calc_rsi_v2_signals(data, rsi_period=14, fast_ma_len=5,
                        buy_gate=40, sell_gate=60,
                        extreme_buy=30, extreme_sell=70,
                        cross_lookback=5, div_window=14):
    """
    计算 RSI v2 的全部序列和信号

    Args:
        data: K 线数据列表 [{'date', 'open', 'high', 'low', 'close'}, ...]
        rsi_period: RSI 周期
        fast_ma_len: 快均线（EMA）周期
        buy_gate: 买入门槛（RSI 低于此值）
        sell_gate: 卖出门槛（RSI 高于此值）
        extreme_buy: 极端买入阈值（RSI 低于此值触发事件1 + 加分）
        extreme_sell: 极端卖出阈值（RSI 高于此值触发事件1 + 加分）
        cross_lookback: 交叉事件的门槛/反向检查窗口
        div_window: 背离比较窗口，也用于极端和近期背离追溯

    Returns:
        {
            'rsi': list,       # RSI 序列（与 data 等长，前面若干个为 None）
            'fast_ma': list,   # RSI 的 EMA 快均线序列
            'signals': list,   # 每个 bar 的信号列表，每项为 list of dict
                               # [{'type': 'B+', 'event': 3}, ...]
        }
    """
    n = len(data)
    closes = [d['close'] for d in data]
    lows = [d['low'] for d in data]
    highs = [d['high'] for d in data]

    # ── 第一层：RSI 计算 ──
    rsi = calc_rsi(closes, rsi_period)

    # ── 第二层：快均线（对 RSI 序列计算 EMA）──
    # calc_ema 接受 list，但 rsi 前面有 None，需要过滤
    # 用有效的 RSI 值计算 EMA，然后对齐回原始长度
    fast_ma = _calc_ema_on_rsi(rsi, fast_ma_len)

    # ── 第三层：信号计算 ──
    signals = [[] for _ in range(n)]
    DIV_MIN_SEP = 2

    # 事件追踪变量
    bars_since_bull_div = 99999
    bars_since_bear_div = 99999
    bars_since_buy_cross = 99999
    bars_since_sell_cross = 99999

    for i in range(n):
        if rsi[i] is None or fast_ma[i] is None:
            continue

        cur_rsi = rsi[i]
        prev_rsi = rsi[i - 1] if i > 0 and rsi[i - 1] is not None else None
        cur_ma = fast_ma[i]
        prev_ma = fast_ma[i - 1] if i > 0 and fast_ma[i - 1] is not None else None

        if prev_rsi is None or prev_ma is None:
            continue

        # ── 事件 1：RSI 下破/上破极端阈值 ──
        # crossunder(rsi, extremeBuy): 前一根 > 阈值，当前 <= 阈值
        if prev_rsi > extreme_buy and cur_rsi <= extreme_buy:
            signals[i].append({'type': 'B', 'event': 1})

        # crossover(rsi, extremeSell): 前一根 < 阈值，当前 >= 阈值
        if prev_rsi < extreme_sell and cur_rsi >= extreme_sell:
            signals[i].append({'type': 'S', 'event': 1})

        # ── 背离检测（事件 3 前置计算）──
        bull_div_alert = False
        bear_div_alert = False

        if i >= DIV_MIN_SEP + 1:
            # 看涨背离：在 divWindow 范围内找参考价格低点
            ref_buy_back = _find_lowest_bar(lows, i, DIV_MIN_SEP, div_window)
            if ref_buy_back is not None:
                ref_idx = i - ref_buy_back
                if (rsi[ref_idx] is not None
                        and lows[i] < lows[ref_idx]
                        and cur_rsi > rsi[ref_idx]
                        and rsi[ref_idx] <= extreme_buy):
                    # 去重：前一根不满足条件才触发
                    prev_raw = _check_bull_div_raw(
                        lows, rsi, i - 1, DIV_MIN_SEP, div_window, extreme_buy)
                    if not prev_raw:
                        bull_div_alert = True

            # 看跌背离：在 divWindow 范围内找参考价格高点
            ref_sell_back = _find_highest_bar(highs, i, DIV_MIN_SEP, div_window)
            if ref_sell_back is not None:
                ref_idx = i - ref_sell_back
                if (rsi[ref_idx] is not None
                        and highs[i] > highs[ref_idx]
                        and cur_rsi < rsi[ref_idx]
                        and rsi[ref_idx] >= extreme_sell):
                    prev_raw = _check_bear_div_raw(
                        highs, rsi, i - 1, DIV_MIN_SEP, div_window, extreme_sell)
                    if not prev_raw:
                        bear_div_alert = True

        # 更新背离追踪
        if bull_div_alert:
            bars_since_bull_div = 0
        else:
            bars_since_bull_div += 1

        if bear_div_alert:
            bars_since_bear_div = 0
        else:
            bars_since_bear_div += 1

        recent_bull_div = bars_since_bull_div <= div_window
        recent_bear_div = bars_since_bear_div <= div_window

        # ── 事件 2：RSI 与快均线交叉 + 门槛 + 升级 ──
        rsi_cross_up = prev_rsi <= prev_ma and cur_rsi > cur_ma
        rsi_cross_down = prev_rsi >= prev_ma and cur_rsi < cur_ma

        # 门槛检查（滚动窗口）
        cross_buy_gate = _rolling_min(rsi, i, cross_lookback) < buy_gate
        cross_sell_gate = _rolling_max(rsi, i, cross_lookback) > sell_gate

        buy_event2 = rsi_cross_up and cross_buy_gate
        sell_event2 = rsi_cross_down and cross_sell_gate

        if buy_event2:
            score = 1
            if _rolling_min(rsi, i, div_window) < extreme_buy:
                score += 1
            if recent_bull_div:
                score += 1
            label = 'B' if score == 1 else ('B+' if score == 2 else 'B++')
            signals[i].append({'type': label, 'event': 2})

        if sell_event2:
            score = 1
            if _rolling_max(rsi, i, div_window) > extreme_sell:
                score += 1
            if recent_bear_div:
                score += 1
            label = 'S' if score == 1 else ('S+' if score == 2 else 'S++')
            signals[i].append({'type': label, 'event': 2})

        # 更新交叉追踪
        if buy_event2:
            bars_since_buy_cross = 0
        else:
            bars_since_buy_cross += 1

        if sell_event2:
            bars_since_sell_cross = 0
        else:
            bars_since_sell_cross += 1

        # ── 事件 3：背离 + 反向检查 ──
        if bull_div_alert:
            score = 2
            if bars_since_buy_cross <= cross_lookback:
                score += 1
            label = 'B+' if score == 2 else 'B++'
            signals[i].append({'type': label, 'event': 3})

        if bear_div_alert:
            score = 2
            if bars_since_sell_cross <= cross_lookback:
                score += 1
            label = 'S+' if score == 2 else 'S++'
            signals[i].append({'type': label, 'event': 3})

    return {
        'rsi': rsi,
        'fast_ma': fast_ma,
        'signals': signals,
    }


# ── 辅助函数 ──────────────────────────────────────────────

def _calc_ema_on_rsi(rsi, period):
    """对 RSI 序列计算 EMA，处理前面的 None 值"""
    n = len(rsi)
    # 找到第一个非 None 的 RSI 索引
    first_valid = None
    for i in range(n):
        if rsi[i] is not None:
            first_valid = i
            break

    if first_valid is None:
        return [None] * n

    # 提取有效部分计算 EMA
    valid_rsi = [rsi[i] for i in range(first_valid, n)]
    valid_ema = calc_ema(valid_rsi, period)

    # 对齐回原始长度
    result = [None] * n
    for j, val in enumerate(valid_ema):
        result[first_valid + j] = val

    return result


def _rolling_min(series, idx, window):
    """计算 series[idx-window+1 .. idx] 的最小值（跳过 None）"""
    start = max(0, idx - window + 1)
    vals = [series[j] for j in range(start, idx + 1) if series[j] is not None]
    return min(vals) if vals else float('inf')


def _rolling_max(series, idx, window):
    """计算 series[idx-window+1 .. idx] 的最大值（跳过 None）"""
    start = max(0, idx - window + 1)
    vals = [series[j] for j in range(start, idx + 1) if series[j] is not None]
    return max(vals) if vals else float('-inf')


def _find_lowest_bar(lows, cur_idx, min_sep, window):
    """
    在 lows[cur_idx - window + 1 .. cur_idx - min_sep] 范围内找最低价所在 bar，
    返回距离 cur_idx 的偏移量（bars back）。找不到返回 None。
    对应 PineScript: ta.lowestbars(low[min_sep], window - min_sep)
    """
    start = max(0, cur_idx - window + 1)
    end = cur_idx - min_sep
    if end < start:
        return None

    min_val = float('inf')
    min_offset = None
    for j in range(start, end + 1):
        if lows[j] < min_val:
            min_val = lows[j]
            min_offset = cur_idx - j

    return min_offset


def _find_highest_bar(highs, cur_idx, min_sep, window):
    """
    在 highs[cur_idx - window + 1 .. cur_idx - min_sep] 范围内找最高价所在 bar，
    返回距离 cur_idx 的偏移量（bars back）。找不到返回 None。
    """
    start = max(0, cur_idx - window + 1)
    end = cur_idx - min_sep
    if end < start:
        return None

    max_val = float('-inf')
    max_offset = None
    for j in range(start, end + 1):
        if highs[j] > max_val:
            max_val = highs[j]
            max_offset = cur_idx - j

    return max_offset


def _check_bull_div_raw(lows, rsi, idx, min_sep, div_window, extreme_buy):
    """检查 idx 位置是否满足看涨背离的原始条件（用于去重）"""
    if idx < min_sep + 1 or rsi[idx] is None:
        return False

    ref_back = _find_lowest_bar(lows, idx, min_sep, div_window)
    if ref_back is None:
        return False

    ref_idx = idx - ref_back
    if rsi[ref_idx] is None:
        return False

    return (lows[idx] < lows[ref_idx]
            and rsi[idx] > rsi[ref_idx]
            and rsi[ref_idx] <= extreme_buy)


def _check_bear_div_raw(highs, rsi, idx, min_sep, div_window, extreme_sell):
    """检查 idx 位置是否满足看跌背离的原始条件（用于去重）"""
    if idx < min_sep + 1 or rsi[idx] is None:
        return False

    ref_back = _find_highest_bar(highs, idx, min_sep, div_window)
    if ref_back is None:
        return False

    ref_idx = idx - ref_back
    if rsi[ref_idx] is None:
        return False

    return (highs[idx] > highs[ref_idx]
            and rsi[idx] < rsi[ref_idx]
            and rsi[ref_idx] >= extreme_sell)
