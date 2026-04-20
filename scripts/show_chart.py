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
from experiments.configs import (
    MARKET_ENVS, DATA_FILE, SMH_FILE, FEE_RATE,
    DEFAULT_TIERS, DEFAULT_ENTRY, DEFAULT_POSITION, DEFAULT_TP,
    BEST_TIERS, BEST_ENTRY, BEST_POSITION, BEST_TP,
)

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
    args = parser.parse_args()

    env = MARKET_ENVS[args.env]
    strat_config = STRATEGIES[args.strategy]
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    print(f"策略：{strat_config['label']}")
    print(f"环境：{env['label']}（{env['start']} ~ {env['end']}）")

    data = load_data(os.path.join(root, DATA_FILE), env['start'], env['end'])
    smh_data = load_data(os.path.join(root, SMH_FILE), env['start'], env['end'])

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

    title = f"SOXL DCA [{strat_config['label']}] — {env['label']}（{env['start']} ~ {env['end']}）"
    show_interactive_chart(data, metrics, title=title, port=args.port)


if __name__ == '__main__':
    main()
