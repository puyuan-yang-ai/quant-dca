"""
ML 信号 vs 各 Entry 规则信号 — 横向对比

用同样的评估标准（Fixed Horizon 5天前瞻收益）对比所有信号的质量。
测试期与 ML 模型一致（后 20% 时间段）。

使用方式:
    cd /home/puyuyang/Projects/quant-dca
    .venv/bin/python -m ml.compare_entry_signals
"""
import sys
import importlib
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

SRC_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SRC_DIR))

DATA_DIR = SRC_DIR / "data"
OUTPUT_DIR = SRC_DIR / "output"


def _load_spy() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "SPY_adjusted.csv")
    df.columns = ["date", "open", "high", "low", "close", "volume"]
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df


def _forward_return(close: pd.Series, horizon: int = 5) -> pd.Series:
    return close.shift(-horizon) / close - 1


def _ema(close: pd.Series, span: int = 20) -> pd.Series:
    return close.ewm(span=span, adjust=False).mean()


def _consecutive_below(close: pd.Series, ema: pd.Series) -> pd.Series:
    below = (close < ema).astype(int)
    result = below.copy()
    for i in range(1, len(result)):
        if result.iloc[i] == 1:
            result.iloc[i] = result.iloc[i - 1] + 1
        else:
            result.iloc[i] = 0
    return result


def compute_all_signals(spy_df: pd.DataFrame) -> dict[str, pd.Series]:
    """计算所有 Entry 信号的逐日布尔 Series"""
    from ml.labeling import compute_backtest_ema_context

    dates = spy_df["date"]
    ema_context = compute_backtest_ema_context(spy_df, ema_period=20)

    signals = {}

    # NDay5 (primary model)
    signals["NDay5"] = ema_context["consecutive_below_ema"] >= 5

    # NDay3
    signals["NDay3"] = ema_context["consecutive_below_ema"] >= 3

    # EMAFilter
    signals["EMAFilter"] = ema_context["sig_ema_filter"]

    # VIX > 30
    vix_df = pd.read_csv(DATA_DIR / "vix_daily.csv")
    vix_df["date"] = pd.to_datetime(vix_df["date"])
    vix_map = dict(zip(vix_df["date"], vix_df["close"]))
    signals["VIX>30"] = pd.Series(
        [vix_map.get(d, 0) > 30 for d in dates], index=spy_df.index
    )

    # Breadth < 20
    breadth_df = pd.read_csv(DATA_DIR / "sp500_breadth.csv")
    breadth_df["date"] = pd.to_datetime(breadth_df["date"])
    breadth_map = dict(zip(breadth_df["date"], breadth_df["breadth"]))
    signals["Breadth<20"] = pd.Series(
        [breadth_map.get(d, 100) < 20 for d in dates], index=spy_df.index
    )

    # SafeHaven > 0.05
    sh_df = pd.read_csv(DATA_DIR / "safe_haven.csv")
    sh_df["date"] = pd.to_datetime(sh_df["date"])
    sh_map = dict(zip(sh_df["date"], sh_df["safe_haven"]))
    signals["SafeHaven"] = pd.Series(
        [sh_map.get(d, 0) > 0.05 for d in dates], index=spy_df.index
    )

    # VIX AND NDay5
    signals["VIX+NDay5"] = signals["VIX>30"] & signals["NDay5"]

    # RSI Signal
    from src.rsi_signals import calc_rsi_v2_signals
    data_list = []
    for _, row in spy_df.iterrows():
        data_list.append({
            "date": row["date"].strftime("%Y-%m-%d"),
            "open": row["open"], "high": row["high"],
            "low": row["low"], "close": row["close"],
        })
    rsi_result = calc_rsi_v2_signals(data_list)
    signals["RSI_v2"] = pd.Series(
        [any(s["type"].startswith("B") for s in sigs) for sigs in rsi_result["signals"]],
        index=spy_df.index,
    )

    return signals


def run_ml_signal(spy_df: pd.DataFrame, test_start_idx: int) -> pd.Series:
    """运行 ML pipeline 并返回测试期的 ML 过滤信号"""
    from ml.labeling import (
        generate_nday_signals,
        create_labels,
        create_labels_sl_proximity,
        create_labels_sl_multi,
    )
    from ml.versions import get_active_config
    from xgboost import XGBClassifier

    config = get_active_config()
    lab_cfg = config["labeling"]
    feat_mod = importlib.import_module(config["features_module"])

    signal = generate_nday_signals(spy_df, n=5)
    lab_method = lab_cfg.get("method", "fixed_horizon")
    if lab_method == "sl_proximity":
        labeled = create_labels_sl_proximity(
            spy_df,
            signal,
            sl_n=lab_cfg.get("sl_n", 7),
            k=lab_cfg.get("k", 3),
        )
    elif lab_method == "sl_multi":
        labeled = create_labels_sl_multi(
            spy_df,
            signal,
            sl_ns=lab_cfg.get("sl_ns", [5, 7]),
            k=lab_cfg.get("k", 3),
        )
    else:
        labeled = create_labels(spy_df, signal, horizon=lab_cfg.get("horizon", 5))
    data, feature_cols = feat_mod.build_features(labeled, spy_df)
    data = data.dropna(subset=feature_cols)

    split_idx = int(len(data) * 0.8)
    train = data.iloc[:split_idx]
    test = data.iloc[split_idx:]

    X_train = train[feature_cols].values
    y_train = train["label"].values
    X_test = test[feature_cols].values

    model = XGBClassifier(
        n_estimators=100, max_depth=4, learning_rate=0.1,
        eval_metric="logloss", random_state=42, verbosity=0,
    )
    model.fit(X_train, y_train)

    proba = model.predict_proba(X_test)[:, 1]
    ml_signal = pd.Series(False, index=spy_df.index)
    test_dates = test["date"].values
    ml_pass_dates = test_dates[proba >= 0.5]
    ml_signal[spy_df["date"].isin(ml_pass_dates)] = True

    return ml_signal, test["date"].iloc[0], test["date"].iloc[-1]


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    spy_df = _load_spy()
    fwd_ret = _forward_return(spy_df["close"], 5)

    print("=" * 60)
    print("  信号横向对比 — Fixed Horizon 5天前瞻收益")
    print("=" * 60)

    # 计算所有规则信号
    print("\n[1/3] 计算规则信号...")
    all_signals = compute_all_signals(spy_df)

    # 计算 ML 信号
    print("[2/3] 训练 ML 模型...")
    ml_signal, test_start, test_end = run_ml_signal(spy_df, 0)
    all_signals["ML_Filter"] = ml_signal

    # 统一评估（只看测试期）
    print("[3/3] 评估对比...\n")
    test_mask = (spy_df["date"] >= test_start) & (spy_df["date"] <= test_end)

    results = []
    for name, sig in all_signals.items():
        active = sig & test_mask
        active_returns = fwd_ret[active].dropna()
        n_signals = active.sum()
        if n_signals == 0:
            results.append({"Signal": name, "Count": 0, "WinRate": 0, "AvgRet": 0, "CumRet": 0})
            continue
        win_rate = (active_returns > 0).mean()
        avg_ret = active_returns.mean()
        cum_ret = active_returns.sum()
        results.append({
            "Signal": name,
            "Count": int(n_signals),
            "WinRate": win_rate,
            "AvgRet": avg_ret,
            "CumRet": cum_ret,
        })

    results_df = pd.DataFrame(results).sort_values("AvgRet", ascending=False)

    print(f"  测试期: {test_start.strftime('%Y-%m-%d')} ~ {test_end.strftime('%Y-%m-%d')}")
    print(f"\n  {'Signal':<15} {'Count':<8} {'WinRate':<10} {'Avg5dRet':<12} {'CumRet':<10}")
    print(f"  {'─'*55}")
    for _, row in results_df.iterrows():
        print(f"  {row['Signal']:<15} {row['Count']:<8} {row['WinRate']:<10.1%} {row['AvgRet']:<12.2%} {row['CumRet']:<10.1%}")

    # 可视化
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle(f"Signal Comparison — Test Period ({test_start.strftime('%Y-%m-%d')} ~ {test_end.strftime('%Y-%m-%d')})",
                 fontsize=13, fontweight="bold")

    plot_df = results_df[results_df["Count"] > 0].copy()

    ax = axes[0]
    colors = ["green" if s == "ML_Filter" else "steelblue" for s in plot_df["Signal"]]
    ax.barh(range(len(plot_df)), plot_df["WinRate"] * 100, color=colors)
    ax.set_yticks(range(len(plot_df)))
    ax.set_yticklabels(plot_df["Signal"])
    ax.set_xlabel("Win Rate (%)")
    ax.set_title("Win Rate by Signal")
    ax.axvline(50, color="red", linestyle="--", alpha=0.5, label="50% baseline")
    ax.legend()

    ax = axes[1]
    ax.barh(range(len(plot_df)), plot_df["AvgRet"] * 100, color=colors)
    ax.set_yticks(range(len(plot_df)))
    ax.set_yticklabels(plot_df["Signal"])
    ax.set_xlabel("Avg 5-day Return (%)")
    ax.set_title("Average Forward Return by Signal")
    ax.axvline(0, color="red", linestyle="--", alpha=0.5)

    plt.tight_layout()
    output_path = OUTPUT_DIR / "ml_signal_comparison.png"
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"\n[Output] 对比图已保存: {output_path}")

    return results_df


if __name__ == "__main__":
    main()
