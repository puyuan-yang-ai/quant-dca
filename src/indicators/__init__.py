"""
技术指标计算模块
提供 EMA、RSI、波动率档口、偏离度、最大涨跌幅等纯函数
"""


def calc_ema(closes, period):
    """
    计算 EMA（指数移动平均）序列

    Args:
        closes: 收盘价列表（按时间正序）
        period: EMA 周期

    Returns:
        与 closes 等长的 EMA 列表。前 period-1 个值为 None（数据不足），
        第 period 个值用 SMA 初始化，之后递推。
    """
    if len(closes) < period:
        return [None] * len(closes)

    alpha = 2.0 / (period + 1)
    ema_values = [None] * len(closes)

    sma = sum(closes[:period]) / period
    ema_values[period - 1] = sma

    for i in range(period, len(closes)):
        ema_values[i] = alpha * closes[i] + (1 - alpha) * ema_values[i - 1]

    return ema_values


def calc_rsi(closes, period=14):
    """
    计算 Wilder RSI 序列

    使用 Wilder 平滑（RMA）计算，与 TradingView 的 ta.rsi() 一致。

    Args:
        closes: 收盘价列表（按时间正序）
        period: RSI 周期（默认 14）

    Returns:
        与 closes 等长的 RSI 列表。前 period 个值为 None（数据不足），
        之后为 0-100 的 RSI 值。
    """
    n = len(closes)
    if n < period + 1:
        return [None] * n

    rsi_values = [None] * n

    # 计算每日涨跌
    gains = []
    losses = []
    for i in range(1, n):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    # 第一个 RMA 值用 SMA 初始化（索引 period-1 对应 closes 的 period）
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    if avg_loss == 0:
        rsi_values[period] = 100.0
    elif avg_gain == 0:
        rsi_values[period] = 0.0
    else:
        rsi_values[period] = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)

    # Wilder 平滑递推（RMA）
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        idx = i + 1  # gains/losses 的索引比 closes 偏移 1
        if avg_loss == 0:
            rsi_values[idx] = 100.0
        elif avg_gain == 0:
            rsi_values[idx] = 0.0
        else:
            rsi_values[idx] = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)

    return rsi_values


def calc_ema_single(closes, period):
    """
    计算最新一个 EMA 值（便捷函数）

    Args:
        closes: 收盘价列表（按时间正序）
        period: EMA 周期

    Returns:
        最新的 EMA 值，数据不足时返回 None
    """
    ema_list = calc_ema(closes, period)
    return ema_list[-1] if ema_list else None


def calc_volatility_tiers(history, lookback=14, percentiles=(30, 60), max_scale=0.90):
    """
    计算波动率动态档口

    Args:
        history: 历史 K 线数据列表（至少 lookback+1 天），每项含 'close' 和 'low'
        lookback: 回看天数
        percentiles: (一档分位数, 二档分位数)
        max_scale: 三档 = 最大跌幅 × max_scale

    Returns:
        (tier1_drop, tier2_drop, tier3_drop) 均为小数形式（如 0.02 表示 2%）
        数据不足时返回 None
    """
    if len(history) < lookback + 1:
        return None

    recent = history[-(lookback + 1):]
    drops = []
    for i in range(1, len(recent)):
        prev_close = recent[i - 1]['close']
        today_low = recent[i]['low']
        drop = max(0.0, (prev_close - today_low) / prev_close)
        drops.append(drop)

    drops.sort()
    n = len(drops)

    tier1 = _percentile(drops, percentiles[0])
    tier2 = _percentile(drops, percentiles[1])
    tier3 = drops[-1] * max_scale

    # 最小档距约束：防止低波动时档口挤在一起
    min_gap_12 = 0.005  # tier2 >= tier1 + 0.5%
    min_gap_23 = 0.010  # tier3 >= tier2 + 1.0%

    if tier2 < tier1 + min_gap_12:
        tier2 = tier1 + min_gap_12
    if tier3 < tier2 + min_gap_23:
        tier3 = tier2 + min_gap_23

    return (tier1, tier2, tier3)


def calc_deviation(close, ema):
    """
    计算偏离度

    Args:
        close: 收盘价
        ema: EMA 值

    Returns:
        偏离度 = (close - ema) / ema，EMA 为 0 或 None 时返回 0.0
    """
    if not ema or ema == 0:
        return 0.0
    return (close - ema) / ema


def calc_max_abs_change(history, lookback=7):
    """
    计算近 N 日最大涨跌幅绝对值

    Args:
        history: 历史 K 线数据列表，每项含 'close'
        lookback: 回看天数

    Returns:
        最大 |日涨跌幅|，数据不足时返回 0.0
    """
    if len(history) < 2:
        return 0.0

    recent = history[-lookback - 1:] if len(history) > lookback + 1 else history
    max_change = 0.0

    for i in range(1, len(recent)):
        prev_close = recent[i - 1]['close']
        if prev_close <= 0:
            continue
        change = abs((recent[i]['close'] - prev_close) / prev_close)
        max_change = max(max_change, change)

    return max_change


def detect_swing_lows(close_prices, dates, n):
    """
    检测 Swing Low（摆动低点 / 局部最低点）

    第 i 天是 swing low 当且仅当 close[i] 严格小于左右各 N 天的所有收盘价。

    Args:
        close_prices: 收盘价列表（按时间正序）
        dates: 日期列表（与 close_prices 等长）
        n: 窗口参数，左右各看 N 天

    Returns:
        [{'date': '2022-06-17', 'price': 373.87}, ...] 按时间正序排列
    """
    result = []
    length = len(close_prices)
    for i in range(n, length - n):
        price = close_prices[i]
        is_low = True
        for j in range(i - n, i):
            if price >= close_prices[j]:
                is_low = False
                break
        if is_low:
            for j in range(i + 1, i + n + 1):
                if price >= close_prices[j]:
                    is_low = False
                    break
        if is_low:
            result.append({'date': dates[i], 'price': price})
    return result


def detect_swing_highs(close_prices, dates, n):
    """
    检测 Swing High（摆动高点 / 局部最高点）

    第 i 天是 swing high 当且仅当 close[i] 严格大于左右各 N 天的所有收盘价。

    Args:
        close_prices: 收盘价列表（按时间正序）
        dates: 日期列表（与 close_prices 等长）
        n: 窗口参数，左右各看 N 天

    Returns:
        [{'date': '2022-01-04', 'price': 477.50}, ...] 按时间正序排列
    """
    result = []
    length = len(close_prices)
    for i in range(n, length - n):
        price = close_prices[i]
        is_high = True
        for j in range(i - n, i):
            if price <= close_prices[j]:
                is_high = False
                break
        if is_high:
            for j in range(i + 1, i + n + 1):
                if price <= close_prices[j]:
                    is_high = False
                    break
        if is_high:
            result.append({'date': dates[i], 'price': price})
    return result


def filter_swing_lows_by_drop(swing_lows, swing_highs, min_drop=0.05):
    """
    最小跌幅过滤：去掉从前一个 swing high 到 swing low 跌幅不足 min_drop 的点

    对每个 swing low，找到它之前最近的 swing high，计算跌幅：
    drop = (high_price - low_price) / high_price
    如果 drop < min_drop，视为横盘噪声，过滤掉。

    Args:
        swing_lows: detect_swing_lows 的输出
        swing_highs: detect_swing_highs 的输出
        min_drop: 最小跌幅阈值（如 0.05 = 5%）

    Returns:
        (kept, filtered) 两个列表，格式与输入相同
    """
    kept = []
    filtered = []
    for low in swing_lows:
        # 找 low 之前最近的 swing high
        prev_high = None
        for high in swing_highs:
            if high['date'] < low['date']:
                prev_high = high
            else:
                break
        if prev_high is None:
            # 没有前置高点，保留
            kept.append(low)
            continue
        drop = (prev_high['price'] - low['price']) / prev_high['price']
        if drop >= min_drop:
            kept.append(low)
        else:
            filtered.append(low)
    return kept, filtered


def _percentile(sorted_list, pct):
    """
    计算已排序列表的分位数（线性插值法）

    Args:
        sorted_list: 已从小到大排序的列表
        pct: 分位数 (0-100)

    Returns:
        分位数值
    """
    if not sorted_list:
        return 0.0

    n = len(sorted_list)
    k = (pct / 100.0) * (n - 1)
    f = int(k)
    c = f + 1

    if f >= n - 1:
        return sorted_list[-1]

    return sorted_list[f] + (k - f) * (sorted_list[c] - sorted_list[f])
