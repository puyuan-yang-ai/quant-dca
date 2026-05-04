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
import csv

from experiments.configs import (
    MARKET_ENVS, DATA_FILE, SMH_FILE, FEE_RATE,
    DEFAULT_TIERS, DEFAULT_ENTRY, DEFAULT_POSITION, DEFAULT_TP,
    BEST_TIERS, BEST_ENTRY, BEST_POSITION, BEST_TP,
)

BREADTH_FILE = 'data/sp500_breadth.csv'

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
    """加载 Market Breadth CSV 数据，按日期范围过滤"""
    if not os.path.exists(filepath):
        print(f"提示：未找到 Breadth 数据文件 {filepath}，跳过 Breadth 副图")
        print(f"  运行 python scripts/fetch_breadth.py 生成数据")
        return None

    breadth_data = []
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if start_date <= row['date'] <= end_date:
                breadth_data.append({
                    'time': row['date'],
                    'value': round(float(row['breadth']), 2),
                })

    if breadth_data:
        print(f"Breadth 数据：{len(breadth_data)} 个交易日")
    return breadth_data if breadth_data else None


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

    # 加载 Breadth 数据
    breadth_data = load_breadth(os.path.join(root, BREADTH_FILE), env['start'], env['end'])

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

    title = f"SPY DCA [{strat_config['label']}] — {env['label']}（{env['start']} ~ {env['end']}）"
    show_interactive_chart(data, metrics, title=title, port=args.port,
                           breadth_data=breadth_data)


if __name__ == '__main__':
    main()
