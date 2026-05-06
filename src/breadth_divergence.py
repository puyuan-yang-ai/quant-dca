"""
Market Breadth 背离检测

检测看多背离：SPY 价格创新低，但 Breadth 未创新低（下跌参与度在减少）。
与 RSI v2 Event 3 逻辑同构，但观察维度不同。

用法：
    from src.breadth_divergence import detect_breadth_divergence
    result = detect_breadth_divergence('data/sp500_breadth.csv', 'data/SPY_adjusted.csv')
    # result['buy_dates']  — set，背离触发日期
    # result['divergences'] — list，背离详情（用于图表画线）
"""
import csv


def _load_breadth(csv_path):
    """加载 Breadth CSV，返回 [(date, value), ...]"""
    records = []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append((row['date'], float(row['breadth'])))
    return records


def _load_spy_close(csv_path):
    """加载 SPY CSV，返回 {date: close}"""
    prices = {}
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            prices[row['时间']] = float(row['收盘价'])
    return prices


def _find_swing_lows(values, window=5):
    """
    识别局部低点（swing low）

    某天的值比前后各 window 天都低 → 标记为 swing low。
    返回索引列表。
    """
    lows = []
    for i in range(window, len(values) - window):
        val = values[i]
        is_low = True
        for j in range(i - window, i + window + 1):
            if j != i and values[j] <= val:
                is_low = False
                break
        if is_low:
            lows.append(i)
    return lows


def detect_breadth_divergence(breadth_csv, spy_csv, threshold=25, window=5):
    """
    检测 Breadth 看多背离

    参数：
        breadth_csv: Breadth CSV 文件路径
        spy_csv: SPY CSV 文件路径
        threshold: 触发区域，Breadth < threshold 时才找背离
        window: swing low 窗口大小（前后各 N 天）

    返回：
        {
            'buy_dates': set,  — 背离触发日期集合
            'divergences': [   — 背离详情列表
                {
                    'date_a': str,      — 前一个低点日期
                    'date_b': str,      — 背离触发日期
                    'breadth_a': float, — 前一个低点 Breadth
                    'breadth_b': float, — 触发点 Breadth
                    'price_a': float,   — 前一个低点 SPY 价格
                    'price_b': float,   — 触发点 SPY 价格
                },
                ...
            ]
        }
    """
    breadth_data = _load_breadth(breadth_csv)
    spy_prices = _load_spy_close(spy_csv)

    # 对齐：只保留 Breadth 和 SPY 都有数据的日期
    aligned = []
    for date, breadth_val in breadth_data:
        if date in spy_prices:
            aligned.append((date, breadth_val, spy_prices[date]))

    if not aligned:
        return {'buy_dates': set(), 'divergences': []}

    dates = [r[0] for r in aligned]
    breadth_values = [r[1] for r in aligned]
    price_values = [r[2] for r in aligned]

    # 1. 找 Breadth 的 swing low
    swing_low_indices = _find_swing_lows(breadth_values, window=window)

    # 2. 筛选触发区域：只保留 Breadth < threshold 的低点
    filtered_lows = [i for i in swing_low_indices if breadth_values[i] < threshold]

    # 3. 检测背离：相邻两个低点，价格新低但 Breadth 未新低
    buy_dates = set()
    divergences = []

    for k in range(1, len(filtered_lows)):
        idx_a = filtered_lows[k - 1]
        idx_b = filtered_lows[k]

        price_a = price_values[idx_a]
        price_b = price_values[idx_b]
        breadth_a = breadth_values[idx_a]
        breadth_b = breadth_values[idx_b]

        # 价格创新低（B < A），但 Breadth 未新低（B > A）
        if price_b < price_a and breadth_b > breadth_a:
            buy_dates.add(dates[idx_b])
            divergences.append({
                'date_a': dates[idx_a],
                'date_b': dates[idx_b],
                'breadth_a': breadth_a,
                'breadth_b': breadth_b,
                'price_a': price_a,
                'price_b': price_b,
            })

    return {'buy_dates': buy_dates, 'divergences': divergences}
