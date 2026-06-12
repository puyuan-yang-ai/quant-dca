"""
特征构造 — 18 个高可解释性特征

布尔特征 (9): 各 Entry 规则在信号日当天是否触发
连续特征 (8): 规则系统底层数据 + 市场状态
离散特征 (1): RSI v2 信号强度

每个特征都能用一句话解释它代表什么市场状态。
"""
import pandas as pd
import numpy as np
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
SRC_DIR = Path(__file__).parent.parent

sys.path.insert(0, str(SRC_DIR))


def _load_vix() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "vix_daily.csv")
    df["date"] = pd.to_datetime(df["date"])
    df = df.rename(columns={"close": "vix"})
    return df[["date", "vix"]]


def _load_breadth() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "sp500_breadth.csv")
    df["date"] = pd.to_datetime(df["date"])
    return df


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _compute_rsi_signal_strength(spy_df: pd.DataFrame) -> pd.Series:
    """
    RSI v2 信号强度: 0=无信号, 1=B, 2=B+, 3=B++
    """
    from src.rsi_signals import calc_rsi_v2_signals

    data = []
    for _, row in spy_df.iterrows():
        data.append({
            "date": row["date"].strftime("%Y-%m-%d"),
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
        })

    result = calc_rsi_v2_signals(data)
    strengths = []
    for sigs in result["signals"]:
        max_strength = 0
        for sig in sigs:
            if sig["type"] == "B":
                max_strength = max(max_strength, 1)
            elif sig["type"] == "B+":
                max_strength = max(max_strength, 2)
            elif sig["type"] == "B++":
                max_strength = max(max_strength, 3)
        strengths.append(max_strength)

    return pd.Series(strengths, index=spy_df.index)


def _compute_entry_signals(spy_df: pd.DataFrame) -> pd.DataFrame:
    """
    计算 9 个 Entry 规则的逐日布尔值。
    独立实现，不依赖 BacktestEngine context。
    """
    from ml.labeling import compute_backtest_ema_context

    dates = spy_df["date"].values

    ema_context = compute_backtest_ema_context(spy_df, ema_period=20)

    # --- Entry rules that depend on BacktestEngine EMA context ---
    sig_ema_filter = ema_context["sig_ema_filter"].values
    sig_nday3 = ema_context["consecutive_below_ema"].values >= 3

    # --- sig_rsi: RSI v2 有买入信号 ---
    from src.rsi_signals import calc_rsi_v2_signals
    data_list = []
    for _, row in spy_df.iterrows():
        data_list.append({
            "date": row["date"].strftime("%Y-%m-%d"),
            "open": row["open"], "high": row["high"],
            "low": row["low"], "close": row["close"],
        })
    rsi_result = calc_rsi_v2_signals(data_list)
    sig_rsi = np.array([
        any(s["type"].startswith("B") for s in sigs)
        for sigs in rsi_result["signals"]
    ])

    # --- sig_breadth: breadth < 20 ---
    breadth_df = _load_breadth()
    breadth_map = dict(zip(breadth_df["date"], breadth_df["breadth"]))
    sig_breadth = np.array([
        breadth_map.get(d, 100) < 20 for d in dates
    ])

    # --- sig_vix: VIX > 30 ---
    vix_df = _load_vix()
    vix_map = dict(zip(vix_df["date"], vix_df["vix"]))
    sig_vix = np.array([
        vix_map.get(d, 0) > 30 for d in dates
    ])

    # --- sig_breadth_consec: breadth_c3 < 20 ---
    bc3_map = {}
    if "breadth_c3" in breadth_df.columns:
        bc3_map = dict(zip(breadth_df["date"], breadth_df["breadth_c3"]))
    sig_breadth_consec = np.array([
        bc3_map.get(d, 100) < 20 for d in dates
    ])

    # --- sig_spread_conv: SpreadConvergence 逻辑 ---
    sig_spread_conv = _compute_spread_convergence(breadth_df, dates)

    # --- sig_breadth_div: BreadthDivergence ---
    from src.breadth_divergence import detect_breadth_divergence
    bd_result = detect_breadth_divergence(
        str(DATA_DIR / "sp500_breadth.csv"),
        str(DATA_DIR / "SPY_adjusted.csv"),
        threshold=25, window=5,
    )
    bd_dates_set = set(pd.to_datetime(list(bd_result["buy_dates"])))
    sig_breadth_div = np.array([d in bd_dates_set for d in dates])

    return pd.DataFrame({
        "sig_ema_filter": sig_ema_filter.astype(int),
        "sig_nday3": sig_nday3.astype(int),
        "sig_rsi": sig_rsi.astype(int),
        "sig_breadth": sig_breadth.astype(int),
        "sig_vix": sig_vix.astype(int),
        "sig_breadth_consec": sig_breadth_consec.astype(int),
        "sig_spread_conv": sig_spread_conv.astype(int),
        "sig_breadth_div": sig_breadth_div.astype(int),
    }, index=spy_df.index)


def _compute_spread_convergence(breadth_df: pd.DataFrame, target_dates) -> np.ndarray:
    """SpreadConvergenceEntry 状态机逻辑（简化版 A: 纯收敛）"""
    if "breadth_c5" not in breadth_df.columns:
        return np.zeros(len(target_dates), dtype=bool)

    rows = breadth_df[["date", "breadth", "breadth_c5"]].dropna().copy()
    buy_dates = set()

    state = "WAITING"
    prev_spread = None

    for _, r in rows.iterrows():
        c1 = r["breadth"]
        c5 = r["breadth_c5"]
        spread = c5 - c1

        if state == "WAITING":
            if c1 < 20:
                state = "OBSERVING"
                prev_spread = spread
                continue
        elif state == "OBSERVING":
            if c1 >= 20:
                state = "WAITING"
                prev_spread = None
                continue
            if prev_spread is not None and spread < prev_spread:
                buy_dates.add(r["date"])

        prev_spread = spread

    return np.array([d in buy_dates for d in target_dates])


def build_features(labeled_df: pd.DataFrame, spy_df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """
    为每个信号日构造特征。

    v3 精简版：移除无效特征，VIX 改为业界标准四级分法。

    移除原因:
    - safe_haven: p=0.75，与标签零相关
    - sig_safe_haven: p=0.29，无显著区分度
    - sig_ema_filter: 常量（NDay5 信号日必然 below EMA），方差为 0
    - sig_nday3: 常量（NDay5 ⊂ NDay3），方差为 0
    - deviation: 与 ema20_dist 完全共线（r=1.0）
    - rsi_signal_strength: p=0.22，不显著
    - sig_rsi: p=0.45，不显著
    - sig_spread_conv: p=0.14，不显著
    - sig_vix: 被 vix_regime 取代

    Returns:
        (data_df, feature_cols)
    """
    from ml.labeling import compute_backtest_ema_context

    df = spy_df.copy()
    close = df["close"]
    ema_context = compute_backtest_ema_context(df, ema_period=20)
    ema20 = pd.to_numeric(ema_context["ema"], errors="coerce")

    # --- 连续特征 ---
    df["rsi_14"] = _rsi(close, 14)
    df["ema20_dist"] = (close / ema20 - 1) * 100

    vix_df = _load_vix()
    breadth_full = _load_breadth()

    df = df.merge(vix_df, on="date", how="left")
    df = df.merge(breadth_full[["date", "breadth", "breadth_c2"]], on="date", how="left")

    df["vix"] = df["vix"].ffill()
    df["breadth"] = df["breadth"].ffill()
    df["breadth_c2"] = df["breadth_c2"].ffill()

    # --- VIX 四级 regime (业界标准: VolRadar/Volatility Box) ---
    # 0=Low(<15), 1=Normal(15-22), 2=Elevated(22-30), 3=Crisis(>30)
    df["vix_regime"] = pd.cut(
        df["vix"], bins=[0, 15, 22, 30, 200], labels=[0, 1, 2, 3]
    ).astype(float)

    # VIX vs 200MA (最强 regime 切换信号)
    vix_200ma = df["vix"].rolling(200, min_periods=50).mean()
    df["vix_above_200ma"] = (df["vix"] > vix_200ma).astype(int)

    # --- 离散特征: consecutive_below_ema ---
    df["consecutive_below_ema"] = ema_context["consecutive_below_ema"].values

    # --- 布尔特征 (只保留统计显著的) ---
    print("  [Features] 计算 Entry 布尔信号...")
    entry_signals = _compute_entry_signals(spy_df)
    for col in entry_signals.columns:
        df[col] = entry_signals[col].values

    # --- 最终特征列表（精简 11 个） ---
    feature_cols = [
        # 连续 (4) — 全部 p<0.05 或核心指标
        "rsi_14",               # r=-0.12, p=0.0002 ✓ 最强
        "ema20_dist",           # 核心趋势位置
        "breadth",              # r=-0.09, p=0.009 ✓
        "breadth_c2",           # r=-0.07, p=0.03 ✓
        # 离散 (3) — regime 信息
        "vix_regime",           # 业界标准四级
        "vix_above_200ma",      # 最强 regime 切换信号
        "consecutive_below_ema",  # r=+0.11, p=0.001 ✓
        # 布尔 (4) — 只保留显著的
        "sig_breadth",          # r=+0.07, p=0.045 ✓
        "sig_breadth_consec",   # 重要度排名第6
        "sig_breadth_div",      # r=+0.08, p=0.015 ✓
        "sig_vix",              # 保留作为 crisis 哨兵
    ]

    signal_dates = labeled_df["date"].values
    feature_rows = df[df["date"].isin(signal_dates)][["date"] + feature_cols].copy()

    result = labeled_df[["date", "label", "forward_return"]].merge(
        feature_rows, on="date", how="left"
    )

    return result, feature_cols
