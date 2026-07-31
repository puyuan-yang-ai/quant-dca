"""
信号生成 + 多种标注方法

支持六种标注:
  1. fixed_horizon: 固定N天远期收益 (原始方案)
  2. triple_barrier: 三重屏障法 (de Prado)
  3. relative_low: 相对低点评估 (买在窗口均价以下)
  4. sl_proximity: Swing Low 邻近度 (是否在底部区域)
  5. sl_price_proximity: Swing Low 价格空间邻近度
  6. sl_multi: 多尺度 Swing Low 邻近度
"""
import sys
import pandas as pd
import numpy as np
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"
sys.path.insert(0, str(ROOT_DIR))


def load_spy() -> pd.DataFrame:
    """加载 SPY 日线数据"""
    df = pd.read_csv(DATA_DIR / "SPY_adjusted.csv")
    df.columns = ["date", "open", "high", "low", "close", "volume"]
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df


def compute_backtest_ema_context(df: pd.DataFrame, ema_period: int = 20) -> pd.DataFrame:
    """
    复刻 BacktestEngine 的 EMA 入场上下文。

    口径（2026-06-26 修正）：用【当日收盘】与【当日 EMA】比较来更新 consecutive_below_ema，
    与按当日收盘决策的实盘一致（尾盘/按收盘价下单时，当日收盘已知）。
    BacktestEngine 已同步为相同口径，保证标签与回测无日期漂移。
    （旧实现用前一日收盘，会让连续天数滞后一天，与 TradingView 看图不一致。）
    """
    from src.indicators import calc_ema

    close = df["close"].astype(float).tolist()
    ema_values = calc_ema(close, ema_period)

    ema_filter = []
    consecutive_below = []
    consecutive_above = []
    below_count = 0
    above_count = 0

    for i, ema_val in enumerate(ema_values):
        cur_close = close[i]
        if ema_val is None:
            below_count = 0
            above_count = 0
            is_below = False
        elif cur_close < ema_val:
            below_count += 1
            above_count = 0
            is_below = True
        else:
            above_count += 1
            below_count = 0
            is_below = False

        ema_filter.append(is_below)
        consecutive_below.append(below_count)
        consecutive_above.append(above_count)

    return pd.DataFrame({
        "ema": ema_values,
        "sig_ema_filter": ema_filter,
        "consecutive_below_ema": consecutive_below,
        "consecutive_above_ema": consecutive_above,
    }, index=df.index)


def generate_nday_signals(df: pd.DataFrame, n: int = 5, ema_period: int = 20) -> pd.Series:
    """
    NDayConfirmEntry(n=5) 逻辑：
    使用 BacktestEngine 同语义的 consecutive_below_ema 触发信号。
    返回布尔 Series，True 表示当天触发买入信号。
    """
    ema_context = compute_backtest_ema_context(df, ema_period)
    return ema_context["consecutive_below_ema"] >= n


def generate_nearbottom_signals(df: pd.DataFrame, n: int = 20, pct: float = 0.03) -> pd.Series:
    """对称"近底"初级信号（路径 A）：收盘距【近 n 日最低价】不超过 pct。

    用滚动低点邻近度（因果，仅用过去 n 根）对称覆盖底部两侧——下跌接近、谷底、
    刚反弹几根都会命中。比"跌破均线"更聚焦"近期低位"，且比标签(近 SL7 底)更松，
    保证候选里正负混合、ML 有事可学。
    """
    low = df["low"].astype(float)
    roll_min = low.rolling(n, min_periods=1).min()
    return df["close"].astype(float) <= roll_min * (1 + pct)


def create_labels(df: pd.DataFrame, signal: pd.Series, horizon: int = 5) -> pd.DataFrame:
    """
    Fixed Horizon Labeling:
    对每个信号日 t，label = 1 if close[t+horizon]/close[t] - 1 > 0 else 0
    """
    future_return = df["close"].shift(-horizon) / df["close"] - 1

    labeled = df[signal].copy()
    labeled["forward_return"] = future_return[signal].values
    labeled["label"] = (labeled["forward_return"] > 0).astype(int)

    labeled = labeled.dropna(subset=["forward_return"])
    return labeled


def create_labels_triple_barrier(
    df: pd.DataFrame,
    signal: pd.Series,
    tp: float = 0.02,
    sl: float = -0.03,
    max_days: int = 20,
) -> pd.DataFrame:
    """
    Triple Barrier Labeling (de Prado):
    对每个信号日 t，向前看最多 max_days 天:
      - 先碰 tp (最高价 >= entry * (1+tp)) → label=1
      - 先碰 sl (最低价 <= entry * (1+sl)) → label=0
      - 到期未触碰任何屏障 → 看收盘收益决定
    返回 forward_return 为实际退出时的收益。
    """
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    dates = df["date"].values
    signal_idx = np.where(signal.values)[0]

    records = []
    for idx in signal_idx:
        entry_price = close[idx]
        if idx + 1 >= len(df):
            continue

        end_idx = min(idx + max_days, len(df) - 1)
        label = None
        exit_ret = None
        exit_day = None

        for j in range(idx + 1, end_idx + 1):
            high_ret = high[j] / entry_price - 1
            low_ret = low[j] / entry_price - 1

            if high_ret >= tp:
                label = 1
                exit_ret = tp
                exit_day = j - idx
                break
            if low_ret <= sl:
                label = 0
                exit_ret = sl
                exit_day = j - idx
                break

        if label is None:
            exit_ret = close[end_idx] / entry_price - 1
            exit_day = end_idx - idx
            label = 1 if exit_ret > 0 else 0

        records.append({
            "date": dates[idx],
            "open": df.iloc[idx]["open"],
            "high": df.iloc[idx]["high"],
            "low": df.iloc[idx]["low"],
            "close": entry_price,
            "volume": df.iloc[idx]["volume"],
            "forward_return": exit_ret,
            "label": label,
            "exit_day": exit_day,
        })

    labeled = pd.DataFrame(records)
    return labeled


def create_labels_relative_low(
    df: pd.DataFrame,
    signal: pd.Series,
    window: int = 20,
) -> pd.DataFrame:
    """
    Relative Low Labeling:
    对每个信号日 t，计算未来 window 天的平均收盘价:
      label = 1 if entry_price < avg(close[t+1 : t+window+1])
    即"我是不是买在了接下来这段时间的相对低位"。
    forward_return = (avg_price - entry) / entry (正数 = 买便宜了)
    """
    close = df["close"].values
    dates = df["date"].values
    signal_idx = np.where(signal.values)[0]

    records = []
    for idx in signal_idx:
        entry_price = close[idx]
        end_idx = idx + window

        if end_idx >= len(df):
            continue

        future_prices = close[idx + 1: end_idx + 1]
        avg_price = future_prices.mean()
        relative_discount = (avg_price - entry_price) / entry_price

        records.append({
            "date": dates[idx],
            "open": df.iloc[idx]["open"],
            "high": df.iloc[idx]["high"],
            "low": df.iloc[idx]["low"],
            "close": entry_price,
            "volume": df.iloc[idx]["volume"],
            "forward_return": relative_discount,
            "label": 1 if entry_price < avg_price else 0,
        })

    labeled = pd.DataFrame(records)
    return labeled


def create_labels_sl_proximity(
    df: pd.DataFrame,
    signal: pd.Series,
    sl_n: int = 7,
    k: int = 3,
) -> pd.DataFrame:
    """
    Swing Low Proximity Labeling:
    对每个信号日 t，找到最近的 SL(sl_n)，如果距离 <= k 个【交易 bar】则 label=1。
    直接回答"信号日是否在底部区域"。
    forward_return = 20天远期收益（用于事后验证信号质量）。

    口径（2026-06-28 修正）：距离以【交易 bar(K线序号差)】度量，而非日历日，
    与系统其余按 bar 的逻辑统一。k=2 表示 SL ±2 bar（5 根窗口）。
    """
    from src.indicators import detect_swing_lows

    close_prices = df["close"].tolist()
    dates_list = df["date"].dt.strftime("%Y-%m-%d").tolist()
    swing_lows = detect_swing_lows(close_prices, dates_list, sl_n)
    sl_date_set = set(s["date"] for s in swing_lows)
    sl_positions = np.array([i for i, ds in enumerate(dates_list) if ds in sl_date_set])

    close = df["close"].values
    dates = df["date"].values
    signal_idx = np.where(signal.values)[0]

    records = []
    for idx in signal_idx:
        entry_price = close[idx]

        if len(sl_positions) == 0:
            continue

        nearest_dist = int(np.abs(sl_positions - idx).min())  # 交易 bar 距离

        fwd_20 = close[idx + 20] / entry_price - 1 if idx + 20 < len(df) else np.nan

        records.append({
            "date": dates[idx],
            "open": df.iloc[idx]["open"],
            "high": df.iloc[idx]["high"],
            "low": df.iloc[idx]["low"],
            "close": entry_price,
            "volume": df.iloc[idx]["volume"],
            "forward_return": fwd_20,
            "label": 1 if nearest_dist <= k else 0,
            "sl_distance": nearest_dist,
        })

    labeled = pd.DataFrame(records)
    labeled = labeled.dropna(subset=["forward_return"])
    return labeled


def build_sl_price_gt(
    df: pd.DataFrame,
    sl_n: int = 7,
    pct: float = 0.008,
) -> pd.DataFrame:
    """
    用 SL(sl_n) 生成全市场价格空间 GT。

    SL 仅负责定义 GT 中心，不参与初级信号筛选。每个 SL 中心只在其自身
    左右各 sl_n 根的定义窗口内生效；窗口内收盘价距离 SL 收盘价不超过 pct
    的交易日标为正例。多个 SL 窗口重叠时，取价格溢价最小的中心。

    时间窗口只限定局部 GT 的作用域，正负标签完全由价格空间距离决定。
    """
    if sl_n < 1:
        raise ValueError("sl_n 必须 >= 1")
    if not 0 < pct < 1:
        raise ValueError("pct 必须位于 (0, 1) 区间")

    from src.indicators import detect_swing_lows

    close = df["close"].astype(float).to_numpy()
    dates_list = df["date"].dt.strftime("%Y-%m-%d").tolist()
    swing_lows = detect_swing_lows(close.tolist(), dates_list, sl_n)
    sl_date_set = {s["date"] for s in swing_lows}
    sl_positions = np.array(
        [i for i, date_str in enumerate(dates_list) if date_str in sl_date_set],
        dtype=int,
    )

    best_premium = np.full(len(df), np.nan, dtype=float)
    best_distance = np.full(len(df), np.nan, dtype=float)

    for sl_idx in sl_positions:
        start = max(0, sl_idx - sl_n)
        end = min(len(df), sl_idx + sl_n + 1)
        bars = np.arange(start, end)
        premiums = close[bars] / close[sl_idx] - 1

        current = best_premium[bars]
        better = np.isnan(current) | (premiums < current)
        update_bars = bars[better]
        best_premium[update_bars] = premiums[better]
        best_distance[update_bars] = np.abs(update_bars - sl_idx)

    is_gt = np.isfinite(best_premium) & (best_premium <= pct)
    price_quality = np.zeros(len(df), dtype=float)
    price_quality[is_gt] = np.clip(
        1 - best_premium[is_gt] / pct,
        0,
        1,
    )

    return pd.DataFrame({
        "is_sl_price_gt": is_gt,
        "sl_price_premium": best_premium,
        "sl_distance": best_distance,
        "price_quality": price_quality,
    }, index=df.index)


def create_labels_sl_price_proximity(
    df: pd.DataFrame,
    signal: pd.Series,
    sl_n: int = 7,
    pct: float = 0.008,
) -> pd.DataFrame:
    """
    Swing Low 价格空间标注。

    对每个初级信号日，直接读取由 build_sl_price_gt 生成的全市场 GT。
    label=1 表示该日收盘价距离局部 SL 收盘价不超过 pct。
    price_quality 仅供训练样本权重使用，不得作为推理特征。
    """
    gt = build_sl_price_gt(df, sl_n=sl_n, pct=pct)
    close = df["close"].astype(float).to_numpy()
    signal_idx = np.where(signal.to_numpy())[0]

    records = []
    for idx in signal_idx:
        entry_price = close[idx]
        fwd_20 = close[idx + 20] / entry_price - 1 if idx + 20 < len(df) else np.nan

        records.append({
            "date": df.iloc[idx]["date"],
            "open": df.iloc[idx]["open"],
            "high": df.iloc[idx]["high"],
            "low": df.iloc[idx]["low"],
            "close": entry_price,
            "volume": df.iloc[idx]["volume"],
            "forward_return": fwd_20,
            "label": int(gt.iloc[idx]["is_sl_price_gt"]),
            "sl_price_premium": gt.iloc[idx]["sl_price_premium"],
            "sl_distance": gt.iloc[idx]["sl_distance"],
            "price_quality": gt.iloc[idx]["price_quality"],
        })

    labeled = pd.DataFrame(records)
    labeled = labeled.dropna(subset=["forward_return"])
    return labeled


def create_labels_sl_multi(
    df: pd.DataFrame,
    signal: pd.Series,
    sl_ns: list[int] = [5, 7],
    k: int = 3,
) -> pd.DataFrame:
    """
    Multi-scale Swing Low Labeling:
    对每个信号日，检查多个尺度的 SL（如 SL5 和 SL7），
    只要任一尺度的最近 SL 距离 <= k 个【交易 bar】，就 label=1。

    口径（2026-06-28 修正）：距离以【交易 bar(K线序号差)】度量，而非日历日。
    """
    from src.indicators import detect_swing_lows

    close_prices = df["close"].tolist()
    dates_list = df["date"].dt.strftime("%Y-%m-%d").tolist()

    all_sl_date_set = set()
    for n in sl_ns:
        sls = detect_swing_lows(close_prices, dates_list, n)
        all_sl_date_set.update(s["date"] for s in sls)
    all_sl_positions = np.array([i for i, ds in enumerate(dates_list) if ds in all_sl_date_set])

    close = df["close"].values
    dates = df["date"].values
    signal_idx = np.where(signal.values)[0]

    records = []
    for idx in signal_idx:
        entry_price = close[idx]

        if len(all_sl_positions) == 0:
            continue

        nearest_dist = int(np.abs(all_sl_positions - idx).min())  # 交易 bar 距离

        fwd_20 = close[idx + 20] / entry_price - 1 if idx + 20 < len(df) else np.nan

        records.append({
            "date": dates[idx],
            "open": df.iloc[idx]["open"],
            "high": df.iloc[idx]["high"],
            "low": df.iloc[idx]["low"],
            "close": entry_price,
            "volume": df.iloc[idx]["volume"],
            "forward_return": fwd_20,
            "label": 1 if nearest_dist <= k else 0,
            "sl_distance": nearest_dist,
        })

    labeled = pd.DataFrame(records)
    labeled = labeled.dropna(subset=["forward_return"])
    return labeled


def run(n_days: int = 5, method: str = "sl_proximity", signal_cfg: dict = None, **kwargs) -> pd.DataFrame:
    """
    完整流程：加载数据 → 生成信号 → 打标签

    method: 'fixed_horizon' | 'triple_barrier' | 'relative_low' |
            'sl_proximity' | 'sl_price_proximity' | 'sl_multi'
    signal_cfg: 初级信号配置。{'type':'nearbottom','n':20,'pct':0.03} 用对称近底规则(路径A)；
                否则用 NDay 门槛（n_days 或 signal_cfg['n_days']）。
    """
    df = load_spy()
    signal_cfg = signal_cfg or {}
    if signal_cfg.get("type") == "nearbottom":
        nb_n = int(signal_cfg.get("n", 20))
        nb_pct = float(signal_cfg.get("pct", 0.03))
        signal = generate_nearbottom_signals(df, n=nb_n, pct=nb_pct)
        sig_desc = f"NearBottom(N={nb_n}, pct={nb_pct})"
    else:
        nd = int(signal_cfg.get("n_days", n_days))
        signal = generate_nday_signals(df, n=nd)
        sig_desc = f"NDay{nd}"

    if method == "fixed_horizon":
        horizon = kwargs.get("horizon", 5)
        labeled = create_labels(df, signal, horizon=horizon)
        desc = f"Fixed Horizon ({horizon}D)"
    elif method == "triple_barrier":
        tp = kwargs.get("tp", 0.02)
        sl = kwargs.get("sl", -0.03)
        max_days = kwargs.get("max_days", 20)
        labeled = create_labels_triple_barrier(df, signal, tp=tp, sl=sl, max_days=max_days)
        desc = f"Triple Barrier (TP={tp*100:.1f}% SL={sl*100:.1f}% N={max_days}D)"
    elif method == "relative_low":
        window = kwargs.get("window", 20)
        labeled = create_labels_relative_low(df, signal, window=window)
        desc = f"Relative Low (window={window}D)"
    elif method == "sl_proximity":
        sl_n = kwargs.get("sl_n", 7)
        k = kwargs.get("k", 3)
        labeled = create_labels_sl_proximity(df, signal, sl_n=sl_n, k=k)
        desc = f"SL{sl_n} Proximity (K={k}天)"
    elif method == "sl_price_proximity":
        sl_n = kwargs.get("sl_n", 7)
        pct = kwargs.get("pct", 0.008)
        labeled = create_labels_sl_price_proximity(df, signal, sl_n=sl_n, pct=pct)
        desc = f"SL{sl_n} Price Proximity (pct={pct:.2%})"
    elif method == "sl_multi":
        sl_ns = kwargs.get("sl_ns", [5, 7])
        k = kwargs.get("k", 3)
        labeled = create_labels_sl_multi(df, signal, sl_ns=sl_ns, k=k)
        desc = f"SL Multi {sl_ns} (K={k}天)"
    else:
        raise ValueError(f"Unknown method: {method}")

    print(f"[Labeling] SPY 数据: {len(df)} 天")
    print(f"[Labeling] 初级信号 {sig_desc} 数: {signal.sum()}")
    print(f"[Labeling] 方法: {desc}")
    print(f"[Labeling] 有效标签数: {len(labeled)}")
    print(f"[Labeling] 正标签比例: {labeled['label'].mean():.1%}")

    return labeled
