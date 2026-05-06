"""
信号策略比较脚本
使用标准化执行层（市价单买1股、无限价单、不止盈），纯粹比较不同 Entry 模块的择时质量。

用法：
  python scripts/compare_signals.py                          # 默认：全量比较（使用现有策略列表）
  python scripts/compare_signals.py --mode nday              # 第一轮：NDay 参数搜索（1-5）
  python scripts/compare_signals.py --mode full --best-nday 3  # 第二轮：全量比较（指定最优 N）

输出：
  各信号策略在 5 个市场环境下的 Sharpe / 最大回撤 / 年化收益率 对比表格
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data_loader import load_data
from src.backtest_engine import BacktestEngine
from src.strategies.composable import ComposableStrategy
from src.modules.tiers import FixedTiers
from src.modules.entry import (
    UnconditionalEntry, EMAFilterEntry, NDayConfirmEntry, RSISignalEntry,
    AndEntry, OrEntry, BreadthEntry, BreadthConsecutiveEntry,
    BreadthDivergenceEntry, VIXEntry, SafeHavenEntry,
    SpreadConvergenceEntry,
)
from src.modules.position import FixedPyramid
from src.modules.take_profit import NoTakeProfit
from experiments.configs import MARKET_ENVS, DATA_FILE, SMH_FILE, FEE_RATE

# ── 标准化执行层（所有信号比较统一使用）──────────────────────
COMPARE_TIERS = FixedTiers(drops=(0.02, 0.05, 0.10))  # 档位值不影响结果（limit_shares 全为 0）
COMPARE_POSITION = FixedPyramid(market_shares=1, limit_shares=(0, 0, 0))
COMPARE_TP = NoTakeProfit()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BREADTH_CSV = os.path.join(ROOT, 'data', 'sp500_breadth.csv')
VIX_CSV = os.path.join(ROOT, 'data', 'vix_daily.csv')
SH_CSV = os.path.join(ROOT, 'data', 'safe_haven.csv')
SPY_CSV = os.path.join(ROOT, 'data', 'SPY_adjusted.csv')


def build_entries_nday():
    """第一轮：NDay 参数搜索（1-5），不依赖 data"""
    entries = {}
    for n in range(1, 6):
        entries[f'NDayConfirm-{n}'] = {
            'label': f'连续{n}天低于EMA',
            'entry': NDayConfirmEntry(n_days=n),
        }
    return entries


def build_entries_vix():
    """VIX 阈值参数搜索"""
    entries = {}
    for t in [30, 35, 40, 45, 50]:
        entries[f'VIX>{t}'] = {
            'label': f'VIX>{t}',
            'entry': VIXEntry(VIX_CSV, threshold=t),
        }
    return entries


def build_entries_safehaven():
    """Safe Haven 阈值参数搜索"""
    entries = {}
    for t in [0.02, 0.05, 0.08, 0.10]:
        entries[f'SH>{t}'] = {
            'label': f'SafeHaven>{t}',
            'entry': SafeHavenEntry(SH_CSV, threshold=t),
        }
    return entries


def build_entries_breadth_div():
    """Breadth 背离参数搜索（threshold）"""
    entries = {}
    for t in [15, 20, 25, 30]:
        entries[f'BreadthDiv-t{t}'] = {
            'label': f'Breadth背离<{t}',
            'entry': BreadthDivergenceEntry(BREADTH_CSV, SPY_CSV, threshold=t),
        }
    return entries


def build_entries_breadth_consec():
    """Breadth 连续弱势曲线阈值搜索（c2~c5 × 阈值 20~34 步长 2）"""
    entries = {}
    for n in [2, 3, 4, 5]:
        for t in range(20, 36, 2):
            entries[f'BreadthC{n}<{t}'] = {
                'label': f'C{n}(≥{n}天)<{t}',
                'entry': BreadthConsecutiveEntry(BREADTH_CSV, n=n, threshold=t),
            }
    return entries


def build_entries_spread_convergence():
    """Breadth spread 收敛信号实验（A: 纯收敛, B: 方向确认）× 停止条件"""
    entries = {}
    stop_thresholds = [1, 2, 3, 5, None]  # None = 无停止条件
    for stop in stop_thresholds:
        label_stop = f'stop={stop}' if stop is not None else '无stop'
        # 实验 A：纯 spread 收敛
        entries[f'A-{label_stop}'] = {
            'label': f'A纯收敛({label_stop})',
            'entry': SpreadConvergenceEntry(BREADTH_CSV, close_threshold=stop, require_c1_rising=False),
        }
        # 实验 B：spread 收敛 + c1 回升
        entries[f'B-{label_stop}'] = {
            'label': f'B方向确认({label_stop})',
            'entry': SpreadConvergenceEntry(BREADTH_CSV, close_threshold=stop, require_c1_rising=True),
        }
    return entries


def build_entries_full(data, best_nday, best_vix=30, best_sh=0.05):
    """第二轮：全量比较，使用指定的最优参数"""
    n = best_nday
    return {
        'Unconditional':        {'label': '无条件每日买入',           'entry': UnconditionalEntry()},
        'EMAFilter':            {'label': 'EMA 均线过滤',             'entry': EMAFilterEntry()},
        f'NDayConfirm-{n}':     {'label': f'连续{n}天低于EMA(best)',  'entry': NDayConfirmEntry(n_days=n)},
        'RSISignal':            {'label': 'RSI v2 信号',              'entry': RSISignalEntry(data)},
        f'AND-NDay{n}+RSI':     {'label': f'NDay{n} AND RSI',        'entry': AndEntry(NDayConfirmEntry(n_days=n), RSISignalEntry(data))},
        f'OR-NDay{n}+RSI':      {'label': f'NDay{n} OR RSI',         'entry': OrEntry(NDayConfirmEntry(n_days=n), RSISignalEntry(data))},
        'Breadth<20':           {'label': 'Breadth<20 恐慌买入',      'entry': BreadthEntry(BREADTH_CSV)},
        f'VIX>{best_vix}':      {'label': f'VIX>{best_vix} 恐慌买入', 'entry': VIXEntry(VIX_CSV, threshold=best_vix)},
        f'SH>{best_sh}':        {'label': f'SafeHaven>{best_sh}',    'entry': SafeHavenEntry(SH_CSV, threshold=best_sh)},
        'BreadthDiv':           {'label': 'Breadth背离',              'entry': BreadthDivergenceEntry(BREADTH_CSV, SPY_CSV)},
    }


def build_entries_legacy(data):
    """兼容旧版：使用硬编码默认参数的策略列表"""
    return build_entries_full(data, best_nday=5, best_vix=30, best_sh=0.05)


def run_comparison(entries_builder, title, needs_data=True):
    """运行信号策略在所有环境下的回测比较"""
    data_path = os.path.join(ROOT, DATA_FILE)
    smh_path = os.path.join(ROOT, SMH_FILE)

    envs_for_score = {k: v for k, v in MARKET_ENVS.items() if v['weight'] > 0}

    results = {}

    print('=' * 72)
    print(f'  {title}')
    print('  标准化执行：市价买1股、无限价单、不止盈')
    print('=' * 72)

    for env_id, env_config in MARKET_ENVS.items():
        data = load_data(data_path, env_config['start'], env_config['end'])
        smh_data = load_data(smh_path, env_config['start'], env_config['end'])

        entries = entries_builder(data) if needs_data else entries_builder()

        print(f"\n{'─' * 72}")
        print(f"  环境: {env_config['label']} ({env_config['start']} ~ {env_config['end']})")
        print(f"{'─' * 72}")
        print(f"  {'策略':<22} {'年化收益':>10} {'最大回撤':>10} {'Sharpe':>8} {'基准Sharpe':>10} {'成本优势':>8} {'买入次数':>8}")
        print(f"  {'-'*22} {'-'*10} {'-'*10} {'-'*8} {'-'*10} {'-'*8} {'-'*8}")

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
            bm_sharpe = metrics.get('benchmark_sharpe', 0)
            cost_adv = metrics.get('cost_advantage', 0) * 100
            buy_count = metrics.get('buy_count', 0)

            print(f"  {config['label']:<22} {ann_ret:>+9.2f}% {max_dd:>9.1f}% {sharpe:>8.2f} {bm_sharpe:>10.2f} {cost_adv:>+7.2f}% {buy_count:>8}")

        # 输出买入持有基准
        bh_ret = metrics.get('bh_annualized_return', 0) * 100
        bh_sharpe = metrics.get('bh_sharpe', 0)
        bh_dd = metrics.get('bh_max_drawdown', 0) * 100
        print(f"  {'── 买入持有基准 ──':<22} {bh_ret:>+9.2f}% {bh_dd:>9.1f}% {'':>8} {bh_sharpe:>10.2f} {'':>8} {'':>8}")

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

    print(f"\n  {'排名':<4} {'策略':<22} {'加权Sharpe':>12}")
    print(f"  {'-'*4} {'-'*22} {'-'*12}")

    for rank, (entry_id, label, score) in enumerate(scores, 1):
        marker = ' ★' if rank == 1 else ''
        print(f"  {rank:<4} {label:<22} {score:>12.4f}{marker}")

    print(f"\n{'=' * 72}")

    # 输出最优策略在各环境的全量指标
    best_id = scores[0][0]
    best_data = results[best_id]
    print(f"\n{'=' * 72}")
    print(f"  最优策略 [{best_data['label']}] 全量指标")
    print(f"{'=' * 72}")

    for env_id, env_config in MARKET_ENVS.items():
        if env_id not in best_data:
            continue
        m = best_data[env_id]
        print(f"\n  ── {env_config['label']} ({env_config['start']} ~ {env_config['end']}) ──")
        print(f"    年化收益率:     {m['annualized_return']*100:+.2f}%")
        print(f"    总收益率:       {m['total_return']*100:+.2f}%")
        print(f"    最大回撤:       {m['max_drawdown']*100:.1f}%")
        print(f"    回撤持续天数:   {m['max_dd_duration']} 交易日")
        print(f"    Sharpe:         {m['sharpe_ratio']:.4f}")
        print(f"    Sortino:        {m['sortino_ratio']:.4f}")
        print(f"    Calmar:         {m['calmar_ratio']:.4f}")
        print(f"    基准可比Sharpe: {m.get('benchmark_sharpe', 0):.4f}")
        print(f"    成本优势比:     {m.get('cost_advantage', 0)*100:+.2f}%")
        print(f"    买入次数:       {m.get('buy_count', 0)}")
        print(f"    ── 买入持有基准 ──")
        print(f"    买入持有年化:   {m.get('bh_annualized_return', 0)*100:+.2f}%")
        print(f"    买入持有Sharpe: {m.get('bh_sharpe', 0):.4f}")
        print(f"    买入持有回撤:   {m.get('bh_max_drawdown', 0)*100:.1f}%")


def main():
    parser = argparse.ArgumentParser(description='信号策略比较')
    parser.add_argument('--mode', type=str, default='default',
                        choices=['default', 'nday', 'vix', 'safehaven', 'breadth-div',
                                 'breadth-consecutive', 'spread-convergence', 'full'],
                        help='运行模式：default=兼容旧版, nday=NDay参数搜索, '
                             'vix=VIX参数搜索, safehaven=SafeHaven参数搜索, '
                             'breadth-div=Breadth背离参数搜索, '
                             'breadth-consecutive=连续弱势曲线阈值搜索, '
                             'spread-convergence=spread收敛信号实验, full=全量比较')
    parser.add_argument('--best-nday', type=int, default=5,
                        help='全量比较时使用的最优 NDay 参数（默认 5）')
    parser.add_argument('--best-vix', type=int, default=30,
                        help='全量比较时使用的最优 VIX 阈值（默认 30）')
    parser.add_argument('--best-sh', type=float, default=0.05,
                        help='全量比较时使用的最优 SafeHaven 阈值（默认 0.05）')
    args = parser.parse_args()

    if args.mode == 'nday':
        run_comparison(
            entries_builder=build_entries_nday,
            title='NDay 参数搜索（NDayConfirm 1-5）',
            needs_data=False,
        )
    elif args.mode == 'vix':
        run_comparison(
            entries_builder=build_entries_vix,
            title='VIX 阈值参数搜索（30/35/40/45/50）',
            needs_data=False,
        )
    elif args.mode == 'safehaven':
        run_comparison(
            entries_builder=build_entries_safehaven,
            title='Safe Haven 阈值参数搜索（0.02/0.05/0.08/0.10）',
            needs_data=False,
        )
    elif args.mode == 'breadth-div':
        run_comparison(
            entries_builder=build_entries_breadth_div,
            title='Breadth 背离参数搜索（threshold=15/20/25/30）',
            needs_data=False,
        )
    elif args.mode == 'breadth-consecutive':
        run_comparison(
            entries_builder=build_entries_breadth_consec,
            title='Breadth 连续弱势曲线阈值搜索（c2~c5 × 阈值 20~34 步长 2）',
            needs_data=False,
        )
    elif args.mode == 'spread-convergence':
        run_comparison(
            entries_builder=build_entries_spread_convergence,
            title='Spread 收敛信号实验（A: 纯收敛 / B: 方向确认 × 停止条件）',
            needs_data=False,
        )
    elif args.mode == 'full':
        n = args.best_nday
        v = args.best_vix
        s = args.best_sh
        run_comparison(
            entries_builder=lambda data: build_entries_full(data, best_nday=n, best_vix=v, best_sh=s),
            title=f'全量信号比较（NDay={n}, VIX={v}, SH={s}）',
            needs_data=True,
        )
    else:
        run_comparison(
            entries_builder=build_entries_legacy,
            title='信号策略比较',
            needs_data=True,
        )


if __name__ == '__main__':
    main()
