"""
实验报告生成器
生成标准化 Markdown 报告，格式与 experiments_result/1-A/ 对齐
"""
import os

from experiments.configs import MARKET_ENVS

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULT_DIR = os.path.join(ROOT_DIR, 'experiments_result')


def _fmt_pct(value):
    """格式化百分比"""
    return f"{value * 100:+.2f}%" if value >= 0 else f"{value * 100:.2f}%"


def _fmt_dollar(value):
    return f"${value:,.2f}"


def generate_experiment_report(exp_id, label, env_name, metrics):
    """生成单个实验在单个环境下的报告"""
    env_label = MARKET_ENVS[env_name]['label']

    order_stats = metrics.get('order_stats', {})
    market_stats = order_stats.get(1.0, {'shares': 0, 'cost': 0, 'count': 0})

    limit_lines = []
    for ratio in sorted(order_stats.keys(), reverse=True):
        if ratio < 1.0:
            s = order_stats[ratio]
            pct = round((1 - ratio) * 100, 1)
            limit_lines.append(
                f"| 跌{pct}% | {s['shares']:,.4f} 股 | {_fmt_dollar(s['cost'])} | {s['count']} 次 |"
            )

    limit_table = '\n'.join(limit_lines) if limit_lines else '| - | - | - | - |'

    content = f"""# 实验 {exp_id} 结果：{label}

## 实验条件

| 参数 | 值 |
|------|-----|
| **实验编号** | {exp_id} |
| **市场周期** | {env_label}（{env_name}） |
| **回测区间** | {metrics['start_date']} ~ {metrics['end_date']} |
| **交易天数** | {metrics['trading_days']} 天 |
| **手续费率** | 1% |

---

## 核心指标

| 指标 | 值 |
|------|-----|
| **总收益率** | {_fmt_pct(metrics['total_return'])} |
| **年化收益率** | {_fmt_pct(metrics['annualized_return'])} |
| **最大回撤** | {metrics['max_drawdown']*100:.2f}% |
| **回撤恢复天数** | {metrics['max_dd_duration']} 天 |
| **Sharpe 比率** | {metrics['sharpe_ratio']:.2f} |
| **Sortino 比率** | {metrics['sortino_ratio']:.2f} |
| **Calmar 比率** | {metrics['calmar_ratio']:.2f} |

## 成本与持仓

| 指标 | 值 |
|------|-----|
| 总投入成本 | {_fmt_dollar(metrics['total_cost'])} |
| SOXL 持股 | {metrics['soxl_shares']:,.4f} 股 |
| SOXL 期末市值 | {_fmt_dollar(metrics['soxl_final_value'])} |
| SMH 持股 | {metrics['smh_shares']:,.4f} 股 |
| SMH 期末市值 | {_fmt_dollar(metrics['smh_final_value'])} |
| 总期末市值 | {_fmt_dollar(metrics['final_value'])} |
| 平均持仓成本 | {_fmt_dollar(metrics['avg_cost'])} |
| 成本优势比 | {_fmt_pct(metrics['cost_advantage'])} |
| 利润分流到 SMH | {_fmt_dollar(metrics['total_diverted'])} |

## 订单统计

| 类型 | 股数 | 金额 | 次数 |
|------|------|------|------|
| 市价单 | {market_stats['shares']:,.4f} 股 | {_fmt_dollar(market_stats['cost'])} | {market_stats['count']} 次 |
{limit_table}

| 统计 | 值 |
|------|-----|
| 限价单挂出 | {metrics['limit_orders_placed']} 次 |
| 限价单成交 | {metrics['limit_orders_filled']} 次 |
| 限价单成交率 | {metrics['limit_fill_rate']*100:.1f}% |
| 止盈触发 | {metrics['tp_trigger_count']} 次 |
| 止盈过期 | {metrics['tp_expire_count']} 次 |
"""
    return content


def generate_stage_comparison(results, best_id, stage_num):
    """生成阶段横向对比报告"""
    stage_names = {1: '档口设置', 2: '入场条件', 3: '仓位分布', 4: '止盈策略'}

    lines = [f"# 第{stage_num}阶段对比：{stage_names.get(stage_num, '')}\n"]
    lines.append(f"**最优方案：{best_id}**\n")

    # 综合评分表
    lines.append("## 综合评分\n")
    lines.append("| 实验 | 方案 | Composite Sharpe | Composite Calmar | 排名 |")
    lines.append("|------|------|-----------------|-----------------|------|")

    ranking = sorted(results.items(), key=lambda x: x[1]['composite_sharpe'], reverse=True)
    for rank, (exp_id, data) in enumerate(ranking, 1):
        marker = " **◀**" if exp_id == best_id else ""
        lines.append(
            f"| {exp_id} | {data['label']} | {data['composite_sharpe']:+.4f} | "
            f"{data['composite_calmar']:+.4f} | #{rank}{marker} |"
        )

    # 各环境详细对比
    lines.append("\n## 各环境详细对比\n")

    for env_name, env_config in MARKET_ENVS.items():
        lines.append(f"\n### {env_config['label']}（{env_name}）\n")
        lines.append("| 实验 | 总收益率 | 年化收益率 | 最大回撤 | Sharpe | Sortino | Calmar | DD恢复天数 |")
        lines.append("|------|---------|----------|---------|--------|---------|--------|-----------|")

        for exp_id, data in results.items():
            m = data['envs'][env_name]
            lines.append(
                f"| {exp_id} | {_fmt_pct(m['total_return'])} | {_fmt_pct(m['annualized_return'])} | "
                f"{m['max_drawdown']*100:.1f}% | {m['sharpe_ratio']:+.2f} | "
                f"{m['sortino_ratio']:+.2f} | {m['calmar_ratio']:+.2f} | "
                f"{m['max_dd_duration']} |"
            )

    return '\n'.join(lines)


def generate_stage_report(results, best_id, stage_num):
    """为一个阶段生成完整报告并写入文件"""
    for exp_id, data in results.items():
        for env_name, metrics in data['envs'].items():
            report = generate_experiment_report(
                exp_id, data['label'], env_name, metrics
            )
            dir_path = os.path.join(RESULT_DIR, exp_id, env_name)
            os.makedirs(dir_path, exist_ok=True)
            with open(os.path.join(dir_path, 'result.md'), 'w', encoding='utf-8') as f:
                f.write(report)

    comparison = generate_stage_comparison(results, best_id, stage_num)
    filepath = os.path.join(RESULT_DIR, f'stage-{stage_num}-comparison.md')
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(comparison)

    print(f"\n报告已生成: {filepath}")


def generate_final_report(results, s1_best, s2_best, s3_best, s4_best):
    """生成最终对比报告"""
    lines = ["# 最终对比：最优组合 vs Baseline\n"]
    lines.append(f"**最优组合**: {s1_best} + {s2_best} + {s3_best} + {s4_best}\n")

    baseline = results.get('baseline', {})
    optimized = results.get('optimized', {})

    if not baseline or not optimized:
        lines.append("\n（数据不完整）\n")
    else:
        lines.append("## 综合评分对比\n")
        lines.append("| 方案 | Composite Sharpe | Composite Calmar |")
        lines.append("|------|-----------------|-----------------|")
        lines.append(
            f"| Baseline | {baseline['composite_sharpe']:+.4f} | "
            f"{baseline['composite_calmar']:+.4f} |"
        )
        lines.append(
            f"| 最优组合 | {optimized['composite_sharpe']:+.4f} | "
            f"{optimized['composite_calmar']:+.4f} |"
        )

        sharpe_diff = optimized['composite_sharpe'] - baseline['composite_sharpe']
        calmar_diff = optimized['composite_calmar'] - baseline['composite_calmar']
        lines.append(
            f"| **提升** | **{sharpe_diff:+.4f}** | **{calmar_diff:+.4f}** |"
        )

        lines.append("\n## 各环境详细对比\n")
        for env_name, env_config in MARKET_ENVS.items():
            lines.append(f"\n### {env_config['label']}（{env_name}）\n")
            lines.append("| 指标 | Baseline | 最优组合 | 差值 |")
            lines.append("|------|---------|---------|------|")

            bm = baseline['envs'][env_name]
            om = optimized['envs'][env_name]

            for key, label in [
                ('total_return', '总收益率'),
                ('annualized_return', '年化收益率'),
                ('max_drawdown', '最大回撤'),
                ('sharpe_ratio', 'Sharpe'),
                ('sortino_ratio', 'Sortino'),
                ('calmar_ratio', 'Calmar'),
                ('max_dd_duration', 'DD恢复天数'),
                ('avg_cost', '平均成本'),
            ]:
                bv = bm[key]
                ov = om[key]
                if key in ('total_return', 'annualized_return', 'max_drawdown', 'cost_advantage'):
                    lines.append(
                        f"| {label} | {bv*100:.2f}% | {ov*100:.2f}% | {(ov-bv)*100:+.2f}% |"
                    )
                elif key == 'avg_cost':
                    lines.append(
                        f"| {label} | ${bv:.2f} | ${ov:.2f} | ${ov-bv:+.2f} |"
                    )
                elif key == 'max_dd_duration':
                    lines.append(
                        f"| {label} | {bv} 天 | {ov} 天 | {ov-bv:+d} 天 |"
                    )
                else:
                    lines.append(
                        f"| {label} | {bv:.2f} | {ov:.2f} | {ov-bv:+.2f} |"
                    )

    content = '\n'.join(lines)
    filepath = os.path.join(RESULT_DIR, 'final-comparison.md')
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"\n最终对比报告已生成: {filepath}")
