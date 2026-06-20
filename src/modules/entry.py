"""
入场条件模块
决定每日是否执行市价买入和/或挂限价单
"""
from src.rsi_signals import calc_rsi_v2_signals


def _extract_buy_dates(data):
    """从 K 线数据中预计算 RSI v2 买入信号日期集合"""
    result = calc_rsi_v2_signals(data)
    buy_dates = set()
    for i, sigs in enumerate(result['signals']):
        for sig in sigs:
            if sig['type'].startswith('B'):
                buy_dates.add(data[i]['date'])
    return buy_dates


class UnconditionalEntry:
    """无条件每日买入：市价单 + 限价单"""

    def should_market_buy(self, context):
        return True

    def should_place_limits(self, context):
        return True

    def __repr__(self):
        return "UnconditionalEntry()"


class EMAFilterEntry:
    """
    EMA 均线过滤

    - 昨收 < EMA → 下跌趋势 → 市价买入 + 限价单（全量买入）
    - 昨收 >= EMA → 上涨趋势 → 仅挂限价单（不追涨，但回调可接）
    """

    def should_market_buy(self, context):
        if context.ema is None:
            return True
        return context.prev_close < context.ema

    def should_place_limits(self, context):
        return True

    def __repr__(self):
        return "EMAFilterEntry()"


class NDayConfirmEntry:
    """
    连续 N 天确认

    连续 N 天收盘价 < EMA 才开始买入（市价 + 限价），否则不买。
    N 值越大，信号越可靠但可能错过机会。
    """

    def __init__(self, n_days=3):
        self.n_days = n_days

    def should_market_buy(self, context):
        return context.consecutive_below_ema >= self.n_days

    def should_place_limits(self, context):
        return context.consecutive_below_ema >= self.n_days

    def __repr__(self):
        return f"NDayConfirmEntry(n={self.n_days})"


class RSISignalEntry:
    """
    RSI v2 信号驱动入场

    当天有 B/B+/B++ 信号时市价买入，无信号不买。
    构造时需传入完整 K 线数据以预计算信号。
    """

    def __init__(self, data):
        self._buy_dates = _extract_buy_dates(data)

    def should_market_buy(self, context):
        return context.day['date'] in self._buy_dates

    def should_place_limits(self, context):
        return False

    def __repr__(self):
        return f"RSISignalEntry(signals={len(self._buy_dates)})"


class BreadthEntry:
    """
    Market Breadth 驱动入场

    Breadth < threshold 时买入（恐慌区抄底）。
    构造时传入 Breadth CSV 路径，预计算满足条件的日期集合。
    """

    def __init__(self, breadth_csv, threshold=20):
        self.threshold = threshold
        self._buy_dates = self._load_buy_dates(breadth_csv, threshold)

    @staticmethod
    def _load_buy_dates(csv_path, threshold):
        import csv as csv_mod
        buy_dates = set()
        with open(csv_path, 'r') as f:
            reader = csv_mod.DictReader(f)
            for row in reader:
                if float(row['breadth']) < threshold:
                    buy_dates.add(row['date'])
        return buy_dates

    def should_market_buy(self, context):
        return context.day['date'] in self._buy_dates

    def should_place_limits(self, context):
        return False

    def __repr__(self):
        return f"BreadthEntry(threshold={self.threshold}, signals={len(self._buy_dates)})"


class VIXEntry:
    """
    VIX 恐慌驱动入场

    VIX > threshold 时买入（市场恐慌区）。
    构造时传入 VIX CSV 路径，预计算满足条件的日期集合。
    """

    def __init__(self, vix_csv, threshold=30):
        self.threshold = threshold
        self._buy_dates = self._load_buy_dates(vix_csv, threshold)

    @staticmethod
    def _load_buy_dates(csv_path, threshold):
        import csv as csv_mod
        buy_dates = set()
        with open(csv_path, 'r') as f:
            reader = csv_mod.DictReader(f)
            for row in reader:
                if float(row['close']) > threshold:
                    buy_dates.add(row['date'])
        return buy_dates

    def should_market_buy(self, context):
        return context.day['date'] in self._buy_dates

    def should_place_limits(self, context):
        return False

    def __repr__(self):
        return f"VIXEntry(threshold={self.threshold}, signals={len(self._buy_dates)})"


class SafeHavenEntry:
    """
    避险需求驱动入场

    Safe Haven（TLT 20日收益 - SPY 20日收益）> threshold 时买入。
    正值表示资金流向国债（避险），此时股票可能被低估。
    构造时传入 Safe Haven CSV 路径，预计算满足条件的日期集合。
    """

    def __init__(self, sh_csv, threshold=0.05):
        self.threshold = threshold
        self._buy_dates = self._load_buy_dates(sh_csv, threshold)

    @staticmethod
    def _load_buy_dates(csv_path, threshold):
        import csv as csv_mod
        buy_dates = set()
        with open(csv_path, 'r') as f:
            reader = csv_mod.DictReader(f)
            for row in reader:
                if float(row['safe_haven']) > threshold:
                    buy_dates.add(row['date'])
        return buy_dates

    def should_market_buy(self, context):
        return context.day['date'] in self._buy_dates

    def should_place_limits(self, context):
        return False

    def __repr__(self):
        return f"SafeHavenEntry(threshold={self.threshold}, signals={len(self._buy_dates)})"


class BreadthConsecutiveEntry:
    """
    Breadth 连续弱势曲线驱动入场

    breadth_cN < threshold 时买入。
    N 表示连续低于 MA20 的天数（2/3/4/5），值越大条件越严格。
    构造时传入 Breadth CSV 路径和参数，预计算满足条件的日期集合。
    """

    def __init__(self, breadth_csv, n, threshold):
        self.n = n
        self.threshold = threshold
        self._buy_dates = self._load_buy_dates(breadth_csv, n, threshold)

    @staticmethod
    def _load_buy_dates(csv_path, n, threshold):
        import csv as csv_mod
        col = f'breadth_c{n}'
        buy_dates = set()
        with open(csv_path, 'r') as f:
            reader = csv_mod.DictReader(f)
            for row in reader:
                if col in row and float(row[col]) < threshold:
                    buy_dates.add(row['date'])
        return buy_dates

    def should_market_buy(self, context):
        return context.day['date'] in self._buy_dates

    def should_place_limits(self, context):
        return False

    def __repr__(self):
        return (f"BreadthConsecutiveEntry(n={self.n}, threshold={self.threshold}, "
                f"signals={len(self._buy_dates)})")


class SpreadConvergenceEntry:
    """
    Breadth 曲线 spread 收敛买入信号（状态机式）

    当 c1(breadth) 进入恐慌区（<20）后，观察 c5-c1 的 spread 是否在收敛，
    收敛时买入。可选右侧停止条件（c3-c1 < close_threshold 时停止买入）。

    参数：
        breadth_csv: Breadth CSV 路径
        close_threshold: c3-c1 < X 时停止买入（None = 无停止条件，只靠 c1>=20 退出）
        require_c1_rising: True = 需要 c1 回升方向确认（实验B），False = 纯收敛（实验A）
    """

    def __init__(self, breadth_csv, close_threshold=None, require_c1_rising=False):
        self.close_threshold = close_threshold
        self.require_c1_rising = require_c1_rising
        self._buy_dates = self._compute(breadth_csv, close_threshold, require_c1_rising)

    @staticmethod
    def _compute(csv_path, close_threshold, require_c1_rising):
        import csv as csv_mod
        # 加载数据
        rows = []
        with open(csv_path, 'r') as f:
            reader = csv_mod.DictReader(f)
            for row in reader:
                if 'breadth_c3' not in row or 'breadth_c5' not in row:
                    continue
                rows.append({
                    'date': row['date'],
                    'c1': float(row['breadth']),
                    'c3': float(row['breadth_c3']),
                    'c5': float(row['breadth_c5']),
                })

        buy_dates = set()
        state = 'WAITING'  # WAITING / OBSERVING / STOPPED
        prev_spread = None
        prev_c1 = None

        for r in rows:
            c1, c3, c5 = r['c1'], r['c3'], r['c5']
            spread = c5 - c1

            if state == 'WAITING':
                if c1 < 20:
                    state = 'OBSERVING'
                    # 第一天进入恐慌区，记录 spread 但不买入（需要昨日数据来判断收敛）
                    prev_spread = spread
                    prev_c1 = c1
                    continue

            elif state == 'OBSERVING':
                if c1 >= 20:
                    state = 'WAITING'
                    prev_spread = None
                    prev_c1 = None
                    continue

                # 检查停止条件
                if close_threshold is not None and (c3 - c1) < close_threshold:
                    state = 'STOPPED'
                    prev_spread = None
                    prev_c1 = None
                    continue

                # 检查买入条件
                if prev_spread is not None and spread < prev_spread:
                    if require_c1_rising:
                        if prev_c1 is not None and c1 > prev_c1:
                            buy_dates.add(r['date'])
                    else:
                        buy_dates.add(r['date'])

            elif state == 'STOPPED':
                if c1 >= 20:
                    state = 'WAITING'
                    prev_spread = None
                    prev_c1 = None
                    continue

            prev_spread = spread
            prev_c1 = c1

        return buy_dates

    def should_market_buy(self, context):
        return context.day['date'] in self._buy_dates

    def should_place_limits(self, context):
        return False

    def __repr__(self):
        ct = self.close_threshold
        mode = 'B(方向确认)' if self.require_c1_rising else 'A(纯收敛)'
        return (f"SpreadConvergenceEntry(stop={ct}, mode={mode}, "
                f"signals={len(self._buy_dates)})")


class BreadthDivergenceEntry:
    """
    Market Breadth 背离驱动入场

    SPY 价格创新低但 Breadth 未创新低时买入（下跌参与度减少 → 底部形成）。
    与 RSI v2 Event 3 逻辑同构。
    构造时传入 Breadth 和 SPY CSV 路径，预计算背离日期集合。
    """

    def __init__(self, breadth_csv, spy_csv, threshold=25, window=5):
        from src.breadth_divergence import detect_breadth_divergence
        self.threshold = threshold
        self.window = window
        result = detect_breadth_divergence(breadth_csv, spy_csv, threshold, window)
        self._buy_dates = result['buy_dates']

    def should_market_buy(self, context):
        return context.day['date'] in self._buy_dates

    def should_place_limits(self, context):
        return False

    def __repr__(self):
        return (f"BreadthDivergenceEntry(threshold={self.threshold}, "
                f"window={self.window}, signals={len(self._buy_dates)})")


class OOSProbaEntry:
    """
    模型样本外概率过滤入场

    传入"模型放行的信号日日期集合"(已是 NDay5 信号 ∩ 概率>阈值 的子集),
    当天日期命中即市价买入。用于经济回测中的 B 组(NDay5 + 模型过滤)。
    日期字符串格式必须与引擎 day['date'] 一致(见调用方做对齐转换)。
    """

    def __init__(self, pass_dates):
        self._buy_dates = set(pass_dates)

    def should_market_buy(self, context):
        return context.day['date'] in self._buy_dates

    def should_place_limits(self, context):
        return False

    def __repr__(self):
        return f"OOSProbaEntry(signals={len(self._buy_dates)})"


class AndEntry:
    """
    通用 AND 组合器

    两个 Entry 同时触发市价买入时才买入。
    用于组合任意两个信号策略，如 VIX + Breadth、NDay + RSI 等。
    """

    def __init__(self, entry_a, entry_b):
        self.a = entry_a
        self.b = entry_b

    def should_market_buy(self, context):
        return self.a.should_market_buy(context) and self.b.should_market_buy(context)

    def should_place_limits(self, context):
        return False

    def __repr__(self):
        return f"AndEntry({self.a!r}, {self.b!r})"


class OrEntry:
    """
    通用 OR 组合器

    两个 Entry 中任一触发市价买入即买入。
    用于组合任意两个信号策略，覆盖面最广。
    """

    def __init__(self, entry_a, entry_b):
        self.a = entry_a
        self.b = entry_b

    def should_market_buy(self, context):
        return self.a.should_market_buy(context) or self.b.should_market_buy(context)

    def should_place_limits(self, context):
        return False

    def __repr__(self):
        return f"OrEntry({self.a!r}, {self.b!r})"
