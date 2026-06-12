"""
交互式图表查看脚本
用法：bash show_chart.sh [--env bear|bull|bear-bull|bull-bear] [--strategy best|baseline] [--port 9870]
默认使用 bear-bull 环境 + best 最优策略
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data_loader import load_data
from src.backtest_engine import BacktestEngine
from src.strategies.composable import ComposableStrategy
from src.interactive_chart import show_interactive_chart
from src.breadth_divergence import detect_breadth_divergence
from src.indicators import detect_swing_lows
import csv

from experiments.configs import (
    MARKET_ENVS, DATA_FILE, SMH_FILE, FEE_RATE,
    DEFAULT_TIERS, DEFAULT_ENTRY, DEFAULT_POSITION, DEFAULT_TP,
    BEST_TIERS, BEST_ENTRY, BEST_POSITION, BEST_TP,
)

BREADTH_FILE = 'data/sp500_breadth.csv'
VIX_FILE = 'data/vix_daily.csv'
SPY_FILE = 'data/SPY_adjusted.csv'

STRATEGIES = {
    'best': {
        'label': '最优组合（1-A+2-C-5+3-B+4-0）',
        'tiers': BEST_TIERS,
        'entry': BEST_ENTRY,
        'position': BEST_POSITION,
        'take_profit': BEST_TP,
    },
    'baseline': {
        'label': 'Baseline',
        'tiers': DEFAULT_TIERS,
        'entry': DEFAULT_ENTRY,
        'position': DEFAULT_POSITION,
        'take_profit': DEFAULT_TP,
    },
}


def load_breadth(filepath, start_date, end_date):
    """加载 Market Breadth CSV 数据（含连续弱势曲线），按日期范围过滤"""
    if not os.path.exists(filepath):
        print(f"提示：未找到 Breadth 数据文件 {filepath}，跳过 Breadth 副图")
        print(f"  运行 python scripts/fetch_breadth.py 生成数据")
        return None, None

    breadth_data = []
    # 连续弱势曲线：{c2: [...], c3: [...], c4: [...], c5: [...]}
    consec_data = {f'c{n}': [] for n in [2, 3, 4, 5]}
    has_consec = False

    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if start_date <= row['date'] <= end_date:
                breadth_data.append({
                    'time': row['date'],
                    'value': round(float(row['breadth']), 2),
                })
                # 如果 CSV 包含连续弱势列
                for n in [2, 3, 4, 5]:
                    col = f'breadth_c{n}'
                    if col in row:
                        has_consec = True
                        consec_data[f'c{n}'].append({
                            'time': row['date'],
                            'value': round(float(row[col]), 2),
                        })

    if breadth_data:
        print(f"Breadth 数据：{len(breadth_data)} 个交易日")
    if has_consec:
        print(f"连续弱势曲线：c2~c5 已加载")

    return (breadth_data if breadth_data else None,
            consec_data if has_consec else None)


def load_vix(filepath, start_date, end_date):
    """加载 VIX 日线 CSV 数据，按日期范围过滤"""
    if not os.path.exists(filepath):
        print(f"提示：未找到 VIX 数据文件 {filepath}，跳过 VIX 副图")
        print(f"  运行 python scripts/fetch_sentiment.py 生成数据")
        return None

    vix_data = []
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if start_date <= row['date'] <= end_date:
                vix_data.append({
                    'time': row['date'],
                    'value': round(float(row['close']), 2),
                })

    if vix_data:
        print(f"VIX 数据：{len(vix_data)} 个交易日")
    return vix_data if vix_data else None


def generate_ml_markers(start_date, end_date):
    """运行 ML pipeline + 推理模式，覆盖到最新 NDay5 信号日。

    流程：
      1. 对有标签的信号做 80/20 切分 → 训练模型 → 预测测试集 (WIN/LOSS)
      2. 对最近无标签的 NDay5 信号也构造特征 → 模型推理 (PRED)
    """
    import importlib
    import pandas as pd
    from ml.labeling import load_spy, generate_nday_signals, create_labels_sl_proximity, create_labels_sl_multi
    from ml.versions import get_active_config
    from xgboost import XGBClassifier

    config = get_active_config()
    feat_mod = importlib.import_module(config["features_module"])
    lab_cfg = config["labeling"]

    spy_df = load_spy()
    signal = generate_nday_signals(spy_df, n=5)

    # --- 有标签的信号（用于训练和回测评估）---
    lab_method = lab_cfg.get("method", "sl_proximity")
    if lab_method == "sl_multi":
        labeled = create_labels_sl_multi(
            spy_df, signal,
            sl_ns=lab_cfg.get("sl_ns", [5, 7]),
            k=lab_cfg.get("k", 3),
        )
    else:
        labeled = create_labels_sl_proximity(
            spy_df, signal,
            sl_n=lab_cfg.get("sl_n", 7),
            k=lab_cfg.get("k", 3),
        )
    data, feature_cols = feat_mod.build_features(labeled, spy_df)
    data = data.dropna(subset=feature_cols)

    split_idx = int(len(data) * 0.8)
    train = data.iloc[:split_idx]
    test = data.iloc[split_idx:]

    model_cfg = config.get("model", {})
    model = XGBClassifier(
        n_estimators=model_cfg.get("n_estimators", 100),
        max_depth=model_cfg.get("max_depth", 4),
        learning_rate=model_cfg.get("learning_rate", 0.1),
        eval_metric="logloss", random_state=42, verbosity=0,
    )
    model.fit(train[feature_cols].values, train["label"].values)

    # --- 推理：找出有标签之外的 NDay5 信号日 ---
    labeled_dates = set(data["date"].values)
    signal_dates = spy_df[signal]["date"].values
    unlabeled_dates = [d for d in signal_dates if d not in labeled_dates]

    unlabeled_signals = []
    if unlabeled_dates:
        unlabeled_df = spy_df[signal & ~spy_df["date"].isin(labeled_dates)].copy()
        dummy_labeled = pd.DataFrame({
            "date": unlabeled_df["date"].values,
            "label": 0,
            "forward_return": float("nan"),
        })
        infer_data, _ = feat_mod.build_features(dummy_labeled, spy_df)
        infer_data = infer_data.dropna(subset=feature_cols)
        if len(infer_data) > 0:
            infer_proba = model.predict_proba(infer_data[feature_cols].values)[:, 1]
            infer_data = infer_data.copy()
            infer_data["proba"] = infer_proba
            unlabeled_signals = infer_data

    # --- 组装 ML 信号列表 ---
    ml_signals = []

    # 测试集（有标签 → WIN/LOSS）
    test = test.copy()
    test["proba"] = model.predict_proba(test[feature_cols].values)[:, 1]
    for _, row in test.iterrows():
        date_str = row["date"].strftime("%Y-%m-%d")
        if date_str < start_date or date_str > end_date:
            continue
        if row["proba"] >= 0.5:
            ml_signals.append({
                "date": date_str,
                "action": "buy",
                "win": row["forward_return"] > 0,
                "ret": row["forward_return"],
                "proba": row["proba"],
            })
        else:
            ml_signals.append({
                "date": date_str,
                "action": "skip",
                "proba": row["proba"],
            })

    # 推理信号（无标签 → PRED）
    pred_buy = pred_skip = 0
    if isinstance(unlabeled_signals, pd.DataFrame) and len(unlabeled_signals) > 0:
        for _, row in unlabeled_signals.iterrows():
            date_str = row["date"].strftime("%Y-%m-%d")
            if date_str < start_date or date_str > end_date:
                continue
            if row["proba"] >= 0.5:
                ml_signals.append({
                    "date": date_str,
                    "action": "buy",
                    "pred": True,
                    "proba": row["proba"],
                })
                pred_buy += 1
            else:
                ml_signals.append({
                    "date": date_str,
                    "action": "skip",
                    "pred": True,
                    "proba": row["proba"],
                })
                pred_skip += 1

    backtest_buy = sum(1 for s in ml_signals if s['action'] == 'buy' and not s.get('pred'))
    backtest_skip = sum(1 for s in ml_signals if s['action'] == 'skip' and not s.get('pred'))
    print(f"ML 信号 — 回测: {backtest_buy} 买入 + {backtest_skip} 跳过 | "
          f"推理: {pred_buy} 买入 + {pred_skip} 跳过")
    return ml_signals


def main():
    parser = argparse.ArgumentParser(description='交互式策略图表查看')
    parser.add_argument('--env', type=str, default='bear-bull',
                        choices=list(MARKET_ENVS.keys()),
                        help='市场环境')
    parser.add_argument('--strategy', type=str, default='best',
                        choices=list(STRATEGIES.keys()),
                        help='策略选择（默认 best 最优策略）')
    parser.add_argument('--port', type=int, default=9870,
                        help='HTTP 服务端口（默认 9870）')
    parser.add_argument('--ml', action='store_true',
                        help='叠加 ML meta-labeling 信号标注')
    args = parser.parse_args()

    env = MARKET_ENVS[args.env]
    strat_config = STRATEGIES[args.strategy]
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    print(f"策略：{strat_config['label']}")
    print(f"环境：{env['label']}（{env['start']} ~ {env['end']}）")

    data = load_data(os.path.join(root, DATA_FILE), env['start'], env['end'])
    smh_data = load_data(os.path.join(root, SMH_FILE), env['start'], env['end'])

    # 加载 Breadth 数据（含连续弱势曲线）
    breadth_data, breadth_consec = load_breadth(os.path.join(root, BREADTH_FILE), env['start'], env['end'])

    # 检测 Swing Low — 使用 GT 标注的尺度 (SL7 only)
    close_prices = [d['close'] for d in data]
    dates = [d['date'] for d in data]
    sl7_all = detect_swing_lows(close_prices, dates, 7)
    print(f"GT Swing Low (SL7)：{len(sl7_all)} 个")
    swing_lows = {'gt7': sl7_all}

    # 计算 Breadth 背离
    breadth_divergences = None
    breadth_path = os.path.join(root, BREADTH_FILE)
    spy_path = os.path.join(root, SPY_FILE)
    if os.path.exists(breadth_path) and os.path.exists(spy_path):
        result = detect_breadth_divergence(breadth_path, spy_path)
        # 过滤到当前环境的日期范围
        divs = [d for d in result['divergences']
                if env['start'] <= d['date_b'] <= env['end']]
        if divs:
            breadth_divergences = divs
            print(f"Breadth 背离：{len(divs)} 个信号")

    strategy = ComposableStrategy(
        tiers=strat_config['tiers'],
        entry=strat_config['entry'],
        position=strat_config['position'],
        take_profit=strat_config['take_profit'],
    )

    print("执行回测...")
    engine = BacktestEngine(data, smh_data, FEE_RATE, strategy)
    metrics = engine.run()

    print(f"总收益率：{metrics['total_return']*100:+.2f}%  "
          f"夏普：{metrics['sharpe_ratio']:.2f}  "
          f"最大回撤：{metrics['max_drawdown']*100:.1f}%")
    print(f"交易记录：{len(metrics.get('trade_log', []))} 笔")

    # ML 信号
    ml_signals = None
    if args.ml:
        print("加载 ML meta-labeling 信号...")
        ml_signals = generate_ml_markers(env['start'], env['end'])

    title = f"SPY DCA [{strat_config['label']}] — {env['label']}（{env['start']} ~ {env['end']}）"
    show_interactive_chart(data, metrics, title=title, port=args.port,
                           breadth_data=breadth_data,
                           breadth_divergences=breadth_divergences,
                           breadth_consec=breadth_consec,
                           swing_lows=swing_lows,
                           show_trades=False,
                           ml_signals=ml_signals)


if __name__ == '__main__':
    main()
