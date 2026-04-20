"""
信号策略比较脚本
使用标准化执行层（市价单买1股、无限价单、不止盈），纯粹比较不同 Entry 模块的择时质量。

用法：
  python scripts/compare_signals.py              # 比较所有信号策略
  bash show_chart.sh --env all                   # 可视化查看具体策略

输出：
  各信号策略在 5 个市场环境下的 Sharpe / 最大回撤 / 年化收益率 对比表格
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
)
from src.modules.position import FixedPyramid
from src.modules.take_profit import NoTakeProfit
from experiments.configs import MARKET_ENVS, DATA_FILE, SMH_FILE, FEE_RATE

# ── 标准化执行层（所有信号比较统一使用）──────────────────────
COMPARE_TIERS = FixedTiers(drops=(0.02, 0.05, 0.10))  # 档位值不影响结果（limit_shares 全为 0）
COMPARE_POSITION = FixedPyramid(market_shares=1, limit_shares=(0, 0, 0))
COMPARE_TP = NoTakeProfit()


def build_entries(data):
    """构建所有待比较的 Entry 候选列表"""
    return {
        'Unconditional':  {'label': '无条件每日买入',     'entry': UnconditionalEntry()},
        'EMAFilter':      {'label': 'EMA 均线过滤',       'entry': EMAFilterEntry()},
        'NDayConfirm-3':  {'label': '连续3天低于EMA',     'entry': NDayConfirmEntry(n_days=3)},
        'NDayConfirm-5':  {'label': '连续5天低于EMA(best)', 'entry': NDayConfirmEntry(n_days=5)},
        'RSISignal':      {'label': 'RSI v2 信号',        'entry': RSISignalEntry(data)},
    }


def run_comparison():
    """运行所有信号策略在所有环境下的回测比较"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_path = os.path.join(root, DATA_FILE)
    smh_path = os.path.join(root, SMH_FILE)

    # 排除 'all' 环境的权重为0，但仍然跑（用于观察，不参与加权）
    envs_for_score = {k: v for k, v in MARKET_ENVS.items() if v['weight'] > 0}

    results = {}  # {entry_id: {env_id: metrics}}

    print('=' * 72)
    print('  信号策略比较（标准化执行：市价买1股、无限价单、不止盈）')
    print('=' * 72)

    # 为每个环境加载数据并运行
    for env_id, env_config in MARKET_ENVS.items():
        data = load_data(data_path, env_config['start'], env_config['end'])
        smh_data = load_data(smh_path, env_config['start'], env_config['end'])

        # RSISignalEntry 需要 data，每个环境要重新构建
        entries = build_entries(data)

        print(f"\n{'─' * 72}")
        print(f"  环境: {env_config['label']} ({env_config['start']} ~ {env_config['end']})")
        print(f"{'─' * 72}")
        print(f"  {'策略':<22} {'年化收益':>10} {'最大回撤':>10} {'Sharpe':>8} {'买入次数':>8}")
        print(f"  {'-'*22} {'-'*10} {'-'*10} {'-'*8} {'-'*8}")

        for entry_id, config in entries.items():
            strategy = ComposableStrategy(
                tiers=COMPARE_TIERS,
                entry=config['entry'],
                position=COMPARE_POSITION,
                take_profit=COMPARE_TP,
            )

            engine = BacktestEngine(data, smh_data, FEE_RATE, strategy)
            metrics = engine.run()

            if entry_id not in results:
                results[entry_id] = {'label': config['label']}
            results[entry_id][env_id] = metrics

            ann_ret = metrics['annualized_return'] * 100
            max_dd = metrics['max_drawdown'] * 100
            sharpe = metrics['sharpe_ratio']
            buy_count = metrics.get('buy_count', 0)

            print(f"  {config['label']:<22} {ann_ret:>+9.2f}% {max_dd:>9.1f}% {sharpe:>8.2f} {buy_count:>8}")

    # 计算加权综合评分
    print(f"\n{'=' * 72}")
    print(f"  综合评分排名（加权 Sharpe）")
    print(f"{'=' * 72}")

    scores = []
    for entry_id, entry_data in results.items():
        weighted_sharpe = 0
        total_weight = 0
        for env_id, env_config in envs_for_score.items():
            if env_id in entry_data:
                w = env_config['weight']
                weighted_sharpe += entry_data[env_id]['sharpe_ratio'] * w
                total_weight += w

        if total_weight > 0:
            weighted_sharpe /= total_weight

        scores.append((entry_id, entry_data['label'], weighted_sharpe))

    scores.sort(key=lambda x: x[2], reverse=True)

    print(f"\n  {'排名':<4} {'策略':<22} {'加权Sharpe':>12} {'备注'}")
    print(f"  {'-'*4} {'-'*22} {'-'*12} {'-'*20}")

    for rank, (entry_id, label, score) in enumerate(scores, 1):
        note = '← Baseline' if entry_id == 'NDayConfirm-5' else ''
        marker = ' ★' if rank == 1 else ''
        print(f"  {rank:<4} {label:<22} {score:>12.4f} {note}{marker}")

    print(f"\n{'=' * 72}")
    winner = scores[0]
    baseline = next((s for s in scores if s[0] == 'NDayConfirm-5'), None)

    if winner[0] == 'NDayConfirm-5':
        print(f"  结论：当前 Baseline (NDayConfirm-5) 仍为最优")
    elif baseline:
        diff = winner[2] - baseline[2]
        print(f"  结论：{winner[1]} (Sharpe {winner[2]:.4f}) beat Baseline (Sharpe {baseline[2]:.4f})")
        print(f"         提升 {diff:+.4f}，建议升级为新 Baseline")
    print(f"{'=' * 72}")


if __name__ == '__main__':
    run_comparison()
