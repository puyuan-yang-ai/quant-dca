"""
信号前瞻验证脚本
验证买入信号发出后 N 天的实际表现，评估信号是否适合期权策略。

核心问题：信号发出后，SPY 是否在 2-4 周内反弹？反弹幅度是否足够？

用法：
  python scripts/validate_signal_returns.py

输出：
  各信号策略在每个环境下的前瞻收益统计：
  - 信号后 5/10/20 日平均涨幅
  - 胜率（涨幅 > 0%, > 1%, > 2%, > 3%）
  - 最大涨幅 / 最大亏损
  - 期权可行性评估
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data_loader import load_data
from src.backtest_engine import BacktestEngine
from src.strategies.composable import ComposableStrategy
from src.modules.tiers import FixedTiers
from src.modules.entry import (
    UnconditionalEntry, EMAFilterEntry, NDayConfirmEntry, RSISignalEntry,
    CombinedAndEntry, CombinedOrEntry,
)
from src.modules.position import FixedPyramid
from src.modules.take_profit import NoTakeProfit
from experiments.configs import MARKET_ENVS, DATA_FILE, SMH_FILE, FEE_RATE

# 标准化执行层
COMPARE_TIERS = FixedTiers(drops=(0.02, 0.05, 0.10))
COMPARE_POSITION = FixedPyramid(market_shares=1, limit_shares=(0, 0, 0))
COMPARE_TP = NoTakeProfit()

# 前瞻窗口
FORWARD_DAYS = [5, 10, 20]

# 期权可行性阈值
OPTION_THRESHOLD = 0.03  # 3% 涨幅作为牛市价差盈利的最低要求


def build_entries(data):
    """构建所有待比较的 Entry 候选列表"""
    return {
        'Unconditional':  {'label': '无条件每日买入',      'entry': UnconditionalEntry()},
        'EMAFilter':      {'label': 'EMA 均线过滤',       'entry': EMAFilterEntry()},
        'NDayConfirm-3':  {'label': '连续3天低于EMA',      'entry': NDayConfirmEntry(n_days=3)},
        'NDayConfirm-5':  {'label': '连续5天低于EMA',      'entry': NDayConfirmEntry(n_days=5)},
        'RSISignal':      {'label': 'RSI v2 信号',        'entry': RSISignalEntry(data)},
        'AND-NDay5+RSI':  {'label': 'NDay5 AND RSI',      'entry': CombinedAndEntry(data, n_days=5)},
        'OR-NDay5+RSI':   {'label': 'NDay5 OR RSI',       'entry': CombinedOrEntry(data, n_days=5)},
    }


def calc_forward_returns(data, buy_dates):
    """
    计算每个买入信号后 N 天的前瞻收益

    Args:
        data: K 线数据列表
        buy_dates: 买入日期集合

    Returns:
        {window: [returns]} — 每个窗口的收益率列表
    """
    # 建立日期 → 索引的映射
    date_to_idx = {d['date']: i for i, d in enumerate(data)}

    results = {w: [] for w in FORWARD_DAYS}
    # 每个信号的详细数据：(日期, 买入价, {窗口: 涨幅}, {窗口: 期间最大回撤}, {窗口: 期间最大涨幅})
    signal_details = []

    for date in sorted(buy_dates):
        if date not in date_to_idx:
            continue
        idx = date_to_idx[date]
        buy_price = data[idx]['close']

        detail = {
            'date': date,
            'buy_price': buy_price,
            'returns': {},
            'max_drawdown': {},
            'max_gain': {},
        }

        for window in FORWARD_DAYS:
            end_idx = idx + window
            if end_idx >= len(data):
                continue

            # 前瞻收益 = 窗口末日收盘价 vs 信号日收盘价
            end_price = data[end_idx]['close']
            fwd_return = (end_price - buy_price) / buy_price

            # 窗口内最大回撤和最大涨幅
            max_dd = 0.0
            max_gain = 0.0
            for j in range(idx + 1, end_idx + 1):
                ret = (data[j]['close'] - buy_price) / buy_price
                if ret < max_dd:
                    max_dd = ret
                if ret > max_gain:
                    max_gain = ret

            results[window].append(fwd_return)
            detail['returns'][window] = fwd_return
            detail['max_drawdown'][window] = max_dd
            detail['max_gain'][window] = max_gain

        signal_details.append(detail)

    return results, signal_details


def print_forward_stats(label, forward_returns, signal_details):
    """打印前瞻收益统计"""
    print(f"\n  {'窗口':<8} {'信号数':>6} {'平均涨幅':>8} {'中位涨幅':>8} {'胜率>0%':>8} {'胜率>1%':>8} {'胜率>2%':>8} {'胜率>3%':>8} {'最大涨':>8} {'最大亏':>8} {'均最大回撤':>10}")
    print(f"  {'-'*8} {'-'*6} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*10}")

    for window in FORWARD_DAYS:
        returns = forward_returns[window]
        if not returns:
            print(f"  {window:>2}日后  {'':>6} — 数据不足 —")
            continue

        n = len(returns)
        avg = sum(returns) / n
        sorted_r = sorted(returns)
        median = sorted_r[n // 2]

        win_0 = sum(1 for r in returns if r > 0) / n * 100
        win_1 = sum(1 for r in returns if r > 0.01) / n * 100
        win_2 = sum(1 for r in returns if r > 0.02) / n * 100
        win_3 = sum(1 for r in returns if r > 0.03) / n * 100

        max_r = max(returns)
        min_r = min(returns)

        # 平均最大回撤（信号后窗口内先跌了多少）
        dds = [d['max_drawdown'].get(window, 0) for d in signal_details if window in d.get('max_drawdown', {})]
        avg_dd = sum(dds) / len(dds) if dds else 0

        print(f"  {window:>2}日后  {n:>6} {avg:>+7.2%} {median:>+7.2%} {win_0:>7.1f}% {win_1:>7.1f}% {win_2:>7.1f}% {win_3:>7.1f}% {max_r:>+7.2%} {min_r:>+7.2%} {avg_dd:>+9.2%}")


def assess_option_viability(forward_returns):
    """评估期权策略可行性"""
    if not forward_returns.get(20):
        return "数据不足"

    returns_20 = forward_returns[20]
    n = len(returns_20)
    win_3 = sum(1 for r in returns_20 if r > OPTION_THRESHOLD) / n * 100

    if win_3 >= 80:
        return f"★★★ 高度可行（20日胜率{win_3:.0f}% > 80%）"
    elif win_3 >= 65:
        return f"★★  可行（20日胜率{win_3:.0f}% > 65%）"
    elif win_3 >= 50:
        return f"★   需谨慎（20日胜率{win_3:.0f}%，刚过半数）"
    else:
        return f"✗   不建议（20日胜率{win_3:.0f}% < 50%）"


def run_validation():
    """运行前瞻收益验证"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_path = os.path.join(root, DATA_FILE)
    smh_path = os.path.join(root, SMH_FILE)

    print('=' * 90)
    print('  信号前瞻验证：买入信号后 N 天的实际表现')
    print('  用途：评估信号是否适合期权策略（牛市价差需要信号后 2-4 周内反弹 3%+）')
    print('=' * 90)

    # 收集所有环境所有策略的期权可行性评估
    viability_summary = {}

    for env_id, env_config in MARKET_ENVS.items():
        data = load_data(data_path, env_config['start'], env_config['end'])
        smh_data = load_data(smh_path, env_config['start'], env_config['end'])

        entries = build_entries(data)

        print(f"\n{'=' * 90}")
        print(f"  环境: {env_config['label']} ({env_config['start']} ~ {env_config['end']})")
        print(f"{'=' * 90}")

        for entry_id, config in entries.items():
            strategy = ComposableStrategy(
                tiers=COMPARE_TIERS,
                entry=config['entry'],
                position=COMPARE_POSITION,
                take_profit=COMPARE_TP,
            )

            engine = BacktestEngine(data, smh_data, FEE_RATE, strategy)
            metrics = engine.run()

            # 从 trade_log 提取市价买入日期
            trade_log = metrics.get('trade_log', [])
            buy_dates = set()
            for trade in trade_log:
                if trade['type'] == 'market_buy':
                    buy_dates.add(trade['date'])

            if not buy_dates:
                print(f"\n  ── {config['label']} ── 无买入信号，跳过")
                continue

            # 计算前瞻收益
            forward_returns, signal_details = calc_forward_returns(data, buy_dates)

            print(f"\n  ── {config['label']}（{len(buy_dates)} 个信号）──")
            print_forward_stats(config['label'], forward_returns, signal_details)

            # 期权可行性评估
            viability = assess_option_viability(forward_returns)
            print(f"\n  期权可行性（20日涨幅>{OPTION_THRESHOLD:.0%}）: {viability}")

            key = entry_id
            if key not in viability_summary:
                viability_summary[key] = {'label': config['label'], 'envs': {}}
            viability_summary[key]['envs'][env_id] = {
                'signal_count': len(buy_dates),
                'viability': viability,
                'win_rate_3pct': (sum(1 for r in forward_returns.get(20, []) if r > OPTION_THRESHOLD) / len(forward_returns.get(20, [1])) * 100) if forward_returns.get(20) else 0,
            }

    # 汇总表
    print(f"\n{'=' * 90}")
    print(f"  期权可行性汇总（20 日内涨幅 > 3% 的胜率）")
    print(f"{'=' * 90}")

    env_labels = {k: v['label'][:4] for k, v in MARKET_ENVS.items()}
    header = f"  {'策略':<22}"
    for env_id in MARKET_ENVS:
        header += f" {env_labels[env_id]:>8}"
    header += f" {'综合评价':>10}"
    print(header)
    print(f"  {'-'*22}" + f" {'-'*8}" * len(MARKET_ENVS) + f" {'-'*10}")

    for entry_id, summary in viability_summary.items():
        line = f"  {summary['label']:<22}"
        rates = []
        for env_id in MARKET_ENVS:
            env_data = summary['envs'].get(env_id, {})
            rate = env_data.get('win_rate_3pct', 0)
            count = env_data.get('signal_count', 0)
            line += f" {rate:>6.0f}%({count:>3})"
            if MARKET_ENVS[env_id]['weight'] > 0:
                rates.append(rate)

        # 加权平均胜率
        if rates:
            weights = [MARKET_ENVS[env_id]['weight'] for env_id in MARKET_ENVS if MARKET_ENVS[env_id]['weight'] > 0]
            weighted_rate = sum(r * w for r, w in zip(rates, weights)) / sum(weights)
            if weighted_rate >= 70:
                verdict = f"★★★ {weighted_rate:.0f}%"
            elif weighted_rate >= 55:
                verdict = f"★★  {weighted_rate:.0f}%"
            elif weighted_rate >= 45:
                verdict = f"★   {weighted_rate:.0f}%"
            else:
                verdict = f"✗   {weighted_rate:.0f}%"
            line += f" {verdict:>10}"

        print(line)

    print(f"\n  说明：百分比 = 信号后 20 日涨幅 > 3% 的概率，括号内 = 信号次数")
    print(f"  ★★★ = 胜率 ≥ 70%（适合期权）  ★★ = 55-70%（可尝试）  ★ = 45-55%（需谨慎）  ✗ = <45%（不建议）")
    print(f"{'=' * 90}")


if __name__ == '__main__':
    run_validation()
