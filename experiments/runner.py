"""
实验批量执行器
自动运行各阶段实验、计算综合评分、选出最优方案
"""
import os
import sys

from src.data_loader import load_data
from src.backtest_engine import BacktestEngine
from src.strategies.composable import ComposableStrategy
from experiments.configs import MARKET_ENVS, DATA_FILE, SMH_FILE, FEE_RATE


def run_single(strategy, env_name, env_config):
    """运行单个实验在单个环境下的回测"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_path = os.path.join(root, DATA_FILE)
    smh_path = os.path.join(root, SMH_FILE)

    data = load_data(data_path, env_config['start'], env_config['end'])
    smh_data = load_data(smh_path, env_config['start'], env_config['end'])

    engine = BacktestEngine(data, smh_data, FEE_RATE, strategy)
    return engine.run()


def run_stage(stage_configs, stage_name=''):
    """
    运行一个阶段的所有实验

    Args:
        stage_configs: {实验ID: {'label', 'tiers', 'entry', 'position', 'take_profit'}}
        stage_name: 阶段名称（用于日志）

    Returns:
        {
            实验ID: {
                'label': str,
                'envs': {环境ID: metrics_dict},
                'composite_sharpe': float,
                'composite_calmar': float,
            }
        }
    """
    results = {}

    for exp_id, config in stage_configs.items():
        strategy = ComposableStrategy(
            tiers=config['tiers'],
            entry=config['entry'],
            position=config['position'],
            take_profit=config['take_profit'],
        )

        print(f"\n{'─'*60}")
        print(f"实验 {exp_id}: {config['label']}")
        print(f"  策略: {strategy}")

        env_results = {}
        composite_sharpe = 0.0
        composite_calmar = 0.0

        for env_name, env_config in MARKET_ENVS.items():
            metrics = run_single(strategy, env_name, env_config)
            env_results[env_name] = metrics

            w = env_config['weight']
            composite_sharpe += w * metrics['sharpe_ratio']
            composite_calmar += w * metrics['calmar_ratio']

            print(f"  [{env_name:10s}] Return: {metrics['total_return']*100:+7.2f}%  "
                  f"Sharpe: {metrics['sharpe_ratio']:+.2f}  "
                  f"MaxDD: {metrics['max_drawdown']*100:.1f}%  "
                  f"Calmar: {metrics['calmar_ratio']:+.2f}")

        results[exp_id] = {
            'label': config['label'],
            'config': config,
            'envs': env_results,
            'composite_sharpe': composite_sharpe,
            'composite_calmar': composite_calmar,
        }

        print(f"  ► Composite Sharpe: {composite_sharpe:+.4f}  "
              f"Composite Calmar: {composite_calmar:+.4f}")

    # 排名（辅助规则：Sharpe 差值 < 0.05 时优先 Calmar）
    ranking = sorted(results.items(), key=lambda x: x[1]['composite_sharpe'], reverse=True)

    best_id = ranking[0][0]
    best_sharpe = ranking[0][1]['composite_sharpe']
    for exp_id, data in ranking[1:]:
        if best_sharpe - data['composite_sharpe'] < 0.05:
            if data['composite_calmar'] > results[best_id]['composite_calmar']:
                best_id = exp_id

    # 高风险降权检查
    for exp_id, data in results.items():
        for env_name, metrics in data['envs'].items():
            if metrics['max_drawdown'] > 0.85:
                if exp_id == best_id:
                    print(f"  ⚠ {exp_id} 在 {env_name} 的 Max DD > 85%，标记为高风险")

    print(f"\n{'═'*60}")
    print(f"{'阶段排名':^60s}")
    print(f"{'═'*60}")
    for rank, (exp_id, data) in enumerate(ranking, 1):
        marker = ' ◀ BEST' if exp_id == best_id else ''
        print(f"  #{rank} {exp_id}: Composite Sharpe = {data['composite_sharpe']:+.4f}  "
              f"Calmar = {data['composite_calmar']:+.4f}{marker}")

    print(f"\n最优方案: {best_id} ({results[best_id]['label']})")

    return results, best_id


def select_best_module(results, best_id, module_name):
    """从最优实验中提取指定模块"""
    return results[best_id]['config'][module_name]


def run_all_experiments():
    """按顺序执行全部 4 个阶段"""
    from experiments.configs import (
        STAGE_1, build_stage_2, build_stage_3, build_stage_4
    )
    from experiments.reporter import generate_stage_report, generate_final_report

    print("=" * 60)
    print("第一阶段：档口设置")
    print("=" * 60)
    s1_results, s1_best = run_stage(STAGE_1, '第一阶段')
    best_tiers = select_best_module(s1_results, s1_best, 'tiers')
    generate_stage_report(s1_results, s1_best, 1)

    print("\n\n" + "=" * 60)
    print("第二阶段：入场条件")
    print("=" * 60)
    stage_2 = build_stage_2(best_tiers)
    s2_results, s2_best = run_stage(stage_2, '第二阶段')
    best_entry = select_best_module(s2_results, s2_best, 'entry')
    generate_stage_report(s2_results, s2_best, 2)

    print("\n\n" + "=" * 60)
    print("第三阶段：仓位分布")
    print("=" * 60)
    stage_3 = build_stage_3(best_tiers, best_entry)
    s3_results, s3_best = run_stage(stage_3, '第三阶段')
    best_position = select_best_module(s3_results, s3_best, 'position')
    generate_stage_report(s3_results, s3_best, 3)

    print("\n\n" + "=" * 60)
    print("第四阶段：止盈策略")
    print("=" * 60)
    stage_4 = build_stage_4(best_tiers, best_entry, best_position)
    s4_results, s4_best = run_stage(stage_4, '第四阶段')
    generate_stage_report(s4_results, s4_best, 4)

    # 回归验证
    print("\n\n" + "=" * 60)
    print("回归验证：最终最优 vs Baseline")
    print("=" * 60)

    from experiments.configs import DEFAULT_TIERS, DEFAULT_ENTRY, DEFAULT_POSITION, DEFAULT_TP
    best_tp = select_best_module(s4_results, s4_best, 'take_profit')

    final_configs = {
        'baseline': {
            'label': 'Baseline（1-A）',
            'tiers': DEFAULT_TIERS,
            'entry': DEFAULT_ENTRY,
            'position': DEFAULT_POSITION,
            'take_profit': DEFAULT_TP,
        },
        'optimized': {
            'label': f'最优组合（{s1_best}+{s2_best}+{s3_best}+{s4_best}）',
            'tiers': best_tiers,
            'entry': best_entry,
            'position': best_position,
            'take_profit': best_tp,
        },
    }
    final_results, final_best = run_stage(final_configs, '回归验证')
    generate_final_report(final_results, s1_best, s2_best, s3_best, s4_best)

    return {
        'stage_1': (s1_results, s1_best),
        'stage_2': (s2_results, s2_best),
        'stage_3': (s3_results, s3_best),
        'stage_4': (s4_results, s4_best),
        'final': (final_results, final_best),
    }
