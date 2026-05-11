"""
月相周期与 SPY 收益率关系验证

用天文算法（ephem 库）计算 1993-2025 年间所有月相转折点，
统计 SPY 在不同月相阶段的收益率差异，验证 Dichev & Janes (2001)
的发现：新月半周期收益率显著高于满月半周期。

方法论说明：
  Dichev & Janes (2001) 定义：
    - "新月半周期" = 以新月为中心的 ±7 天（下弦→新月→上弦）
    - "满月半周期" = 以满月为中心的 ±7 天（上弦→满月→下弦）
  本脚本同时实现两种分析方案：
    方案 A（事件驱动）: 在每个新月/满月事件日计算 N 天前向收益（独立样本）
    方案 B（日收益率）: 每个交易日按距最近月相分组，比较日均收益率

用法：
    python scripts/lunar_analysis.py
"""

import csv
import math
import os
from datetime import datetime, timedelta

import ephem
from scipy import stats

# ─────────────────────────── 常量 ───────────────────────────

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
SPY_FILE = os.path.join(DATA_DIR, 'SPY_adjusted.csv')

HOLDING_PERIODS = [7, 15]

SUB_PERIODS = [
    ('1993-2000', '1993-01-01', '2000-12-31'),
    ('2001-2009', '2001-01-01', '2009-12-31'),
    ('2010-2019', '2010-01-01', '2019-12-31'),
    ('2020-2025', '2020-01-01', '2025-12-31'),
]

# 4 段月相名称（以各月相为中心，不是"从 X 到 Y"）
PHASE_NAMES_4 = ['新月附近', '上弦附近', '满月附近', '下弦附近']


# ─────────────────────── 数据加载 ────────────────────────

def load_spy_data():
    """加载 SPY 日线数据"""
    prices = {}
    dates = []
    with open(SPY_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            date_str = row['时间']
            prices[date_str] = float(row['收盘价'])
            dates.append(date_str)
    dates.sort()
    return prices, dates


# ─────────────────────── 月相计算 ────────────────────────

def compute_lunar_events(start_year=1993, end_year=2025):
    """计算所有新月、上弦月、满月、下弦月的日期"""
    events = {'new_moon': [], 'first_quarter': [], 'full_moon': [], 'last_quarter': []}
    start = ephem.Date(f'{start_year}/1/1')
    end = ephem.Date(f'{end_year + 1}/1/1')

    funcs = {
        'new_moon': ephem.next_new_moon,
        'first_quarter': ephem.next_first_quarter_moon,
        'full_moon': ephem.next_full_moon,
        'last_quarter': ephem.next_last_quarter_moon,
    }
    for phase_name, func in funcs.items():
        d = start
        while d < end:
            d = func(d)
            if d < end:
                events[phase_name].append(ephem.Date(d).datetime().strftime('%Y-%m-%d'))
                d += 1
    return events


def nearest_trading_day(target_date, dates_set):
    """找到距目标日期最近的交易日（往后找）"""
    if target_date in dates_set:
        return target_date
    dt = datetime.strptime(target_date, '%Y-%m-%d')
    for i in range(1, 10):
        c = (dt + timedelta(days=i)).strftime('%Y-%m-%d')
        if c in dates_set:
            return c
    return None


def trading_day_offset(start_date, offset, dates_list):
    """从 start_date 往后数 offset 个交易日"""
    try:
        idx = dates_list.index(start_date)
    except ValueError:
        return None
    t = idx + offset
    return dates_list[t] if t < len(dates_list) else None


# ─────────── 方案 A：事件驱动（独立样本） ──────────────

def event_driven_returns(event_dates, dates_set, dates_list, prices, holding_period):
    """对每个月相事件日，计算 N 天前向收益（独立样本）"""
    returns = []
    for ed in event_dates:
        td = nearest_trading_day(ed, dates_set)
        if not td:
            continue
        target = trading_day_offset(td, holding_period, dates_list)
        if target and target in prices:
            returns.append((prices[target] - prices[td]) / prices[td])
    return returns


# ─────────── 方案 B：日收益率分组 ──────────────

def assign_daily_phase_centered(dates_list, events):
    """
    为每个交易日分配月相阶段——以各月相为中心（Dichev & Janes 方法）。

    每个交易日归入距其最近的月相事件对应的阶段：
      0 = 新月附近，1 = 上弦附近，2 = 满月附近，3 = 下弦附近

    这样 "新月半周期" = Phase 0（新月附近）
         "满月半周期" = Phase 2（满月附近）
    与论文定义一致。
    """
    # 构建所有月相事件的有序列表：(date_str, phase_index)
    all_events = []
    phase_idx = {'new_moon': 0, 'first_quarter': 1, 'full_moon': 2, 'last_quarter': 3}
    for phase_name, idx in phase_idx.items():
        for d in events[phase_name]:
            all_events.append((d, idx))
    all_events.sort()

    if not all_events:
        return {}

    result = {}
    event_idx = 0
    for td in dates_list:
        # 找到 td 前后最近的两个事件
        while event_idx + 1 < len(all_events) and all_events[event_idx + 1][0] <= td:
            event_idx += 1

        # 比较与前后两个事件的距离
        td_dt = datetime.strptime(td, '%Y-%m-%d')

        curr_event = all_events[event_idx]
        curr_dist = abs((td_dt - datetime.strptime(curr_event[0], '%Y-%m-%d')).days)
        best_phase = curr_event[1]
        best_dist = curr_dist

        if event_idx + 1 < len(all_events):
            next_event = all_events[event_idx + 1]
            next_dist = abs((td_dt - datetime.strptime(next_event[0], '%Y-%m-%d')).days)
            if next_dist < best_dist:
                best_phase = next_event[1]

        result[td] = best_phase

    return result


def compute_daily_returns(dates_list, prices):
    """计算每日收益率"""
    daily_rets = {}
    for i in range(1, len(dates_list)):
        prev, curr = dates_list[i - 1], dates_list[i]
        daily_rets[curr] = (prices[curr] - prices[prev]) / prices[prev]
    return daily_rets


# ────────────────────── 统计工具 ──────────────────────

def desc_stats(returns):
    """描述性统计"""
    if not returns:
        return {'n': 0, 'mean': 0, 'median': 0, 'std': 0, 'win_rate': 0}
    n = len(returns)
    mean = sum(returns) / n
    s = sorted(returns)
    median = s[n // 2] if n % 2 == 1 else (s[n // 2 - 1] + s[n // 2]) / 2
    std = math.sqrt(sum((r - mean) ** 2 for r in returns) / n)
    win_rate = sum(1 for r in returns if r > 0) / n
    return {'n': n, 'mean': mean, 'median': median, 'std': std, 'win_rate': win_rate}


def cohens_d(g1, g2):
    """Cohen's d 效应量"""
    n1, n2 = len(g1), len(g2)
    if n1 == 0 or n2 == 0:
        return 0
    m1, m2 = sum(g1) / n1, sum(g2) / n2
    v1 = sum((x - m1) ** 2 for x in g1) / n1
    v2 = sum((x - m2) ** 2 for x in g2) / n2
    ps = math.sqrt((v1 * n1 + v2 * n2) / (n1 + n2))
    return (m1 - m2) / ps if ps > 0 else 0


def effect_label(d):
    ad = abs(d)
    if ad < 0.2:
        return '微小效应'
    elif ad < 0.5:
        return '小效应'
    elif ad < 0.8:
        return '中效应'
    return '大效应'


# ────────────────────── 输出 ──────────────────────

SEP = '─' * 78


def print_event_comparison(new_rets, full_rets, hp, label=''):
    """打印事件驱动法的新月 vs 满月对比"""
    sn = desc_stats(new_rets)
    sf = desc_stats(full_rets)
    diff = sn['mean'] - sf['mean']

    if len(new_rets) > 1 and len(full_rets) > 1:
        t_stat, t_pval = stats.ttest_ind(new_rets, full_rets)
        u_stat, u_pval = stats.mannwhitneyu(new_rets, full_rets, alternative='two-sided')
        d = cohens_d(new_rets, full_rets)
    else:
        t_stat, t_pval, u_stat, u_pval, d = 0, 1, 0, 1, 0

    title = f'新月后 vs 满月后（{hp} 天持仓）'
    if label:
        title = f'[{label}] {title}'
    print(f'\n{title}')
    print(SEP)
    print(f'  {"":14} {"新月后":>10} {"满月后":>10} {"差异":>10} {"p-value":>10}')
    print(f'  {"均值":<14} {sn["mean"]:>+9.3%} {sf["mean"]:>+9.3%} '
          f'{diff:>+9.3%} {t_pval:>10.4f}')
    print(f'  {"中位数":<12} {sn["median"]:>+9.3%} {sf["median"]:>+9.3%} '
          f'{sn["median"] - sf["median"]:>+9.3%}')
    print(f'  {"胜率":<14} {sn["win_rate"]:>9.1%} {sf["win_rate"]:>9.1%} '
          f'{sn["win_rate"] - sf["win_rate"]:>+9.1%}')
    print(f'  {"样本数":<12} {sn["n"]:>9} {sf["n"]:>9}')
    print()
    print(f'  t 检验:        t = {t_stat:+.3f},  p = {t_pval:.4f}')
    print(f'  Mann-Whitney:  U = {u_stat:.0f},  p = {u_pval:.4f}')
    print(f'  Cohen\'s d:     {d:+.4f}  ({effect_label(d)})')
    annual = diff * (252 / hp)
    print(f'  年化收益差异:  {annual:+.2%}')
    return diff, t_pval


def print_daily_comparison(new_rets, full_rets, label=''):
    """打印日收益率分组法的新月 vs 满月对比"""
    sn = desc_stats(new_rets)
    sf = desc_stats(full_rets)
    diff = sn['mean'] - sf['mean']

    if len(new_rets) > 1 and len(full_rets) > 1:
        t_stat, t_pval = stats.ttest_ind(new_rets, full_rets)
        d = cohens_d(new_rets, full_rets)
    else:
        t_stat, t_pval, d = 0, 1, 0

    title = '新月附近 vs 满月附近（日收益率）'
    if label:
        title = f'[{label}] {title}'
    print(f'\n{title}')
    print(SEP)
    print(f'  {"":14} {"新月附近":>12} {"满月附近":>12} {"差异":>12}')
    print(f'  {"日均收益":<12} {sn["mean"]:>+11.5%} {sf["mean"]:>+11.5%} '
          f'{diff:>+11.5%}')
    print(f'  {"胜率":<14} {sn["win_rate"]:>11.1%} {sf["win_rate"]:>11.1%} '
          f'{sn["win_rate"] - sf["win_rate"]:>+11.1%}')
    print(f'  {"样本(天)":<10} {sn["n"]:>11} {sf["n"]:>11}')
    print()
    print(f'  t 检验:        t = {t_stat:+.3f},  p = {t_pval:.4f}')
    print(f'  Cohen\'s d:     {d:+.4f}  ({effect_label(d)})')
    print(f'  年化收益差异:  {diff * 252:+.2%}')
    return diff, t_pval


# ────────────────────── 主逻辑 ──────────────────────

def main():
    print('=' * 78)
    print('  月相周期与 SPY 收益率关系验证')
    print('  对照基准：Dichev & Janes (2001), Yuan et al. (2006)')
    print('=' * 78)

    # ── 加载数据 ──
    print('\n加载 SPY 数据...')
    prices, dates_list = load_spy_data()
    dates_set = set(dates_list)
    print(f'  数据范围：{dates_list[0]} ~ {dates_list[-1]}')
    print(f'  交易日数：{len(dates_list)}')

    # ── 计算月相 ──
    print('\n计算月相日期（ephem 天文算法）...')
    events = compute_lunar_events(1993, 2025)
    for name, label in [('new_moon', '新月'), ('first_quarter', '上弦'),
                        ('full_moon', '满月'), ('last_quarter', '下弦')]:
        print(f'  {label}：{len(events[name])} 次')

    # ══════════════════════════════════════════════════════
    # 方案 A：事件驱动法（独立样本，每个事件只算一次）
    # ══════════════════════════════════════════════════════
    print('\n' + '=' * 78)
    print('  方案 A：事件驱动法（每个新月/满月事件计算 N 天前向收益）')
    print('  样本独立，每种约 400 个')
    print('=' * 78)

    for hp in HOLDING_PERIODS:
        new_rets = event_driven_returns(events['new_moon'], dates_set, dates_list, prices, hp)
        full_rets = event_driven_returns(events['full_moon'], dates_set, dates_list, prices, hp)
        print_event_comparison(new_rets, full_rets, hp)

    # ── 方案 A 稳定性验证 ──
    print('\n' + '=' * 78)
    print('  方案 A 稳定性验证（15 天持仓）')
    print('=' * 78)

    hp = 15
    print(f'\n  {"时期":<12} {"新月后均值":>10} {"满月后均值":>10} '
          f'{"差异":>9} {"p-value":>9} {"N→>F":>6}')
    print(f'  {SEP}')
    for label, start, end in SUB_PERIODS:
        sub_new = [d for d in events['new_moon'] if start <= d <= end]
        sub_full = [d for d in events['full_moon'] if start <= d <= end]
        nr = event_driven_returns(sub_new, dates_set, dates_list, prices, hp)
        fr = event_driven_returns(sub_full, dates_set, dates_list, prices, hp)
        sn, sf = desc_stats(nr), desc_stats(fr)
        diff = sn['mean'] - sf['mean']
        _, pval = stats.ttest_ind(nr, fr) if len(nr) > 1 and len(fr) > 1 else (0, 1)
        flag = '是' if diff > 0 else '否'
        print(f'  {label:<12} {sn["mean"]:>+9.3%} {sf["mean"]:>+9.3%} '
              f'{diff:>+8.3%} {pval:>9.4f} {flag:>6}')

    # ══════════════════════════════════════════════════════
    # 方案 B：日收益率分组法（Dichev & Janes 核心方法）
    # ══════════════════════════════════════════════════════
    print('\n' + '=' * 78)
    print('  方案 B：日收益率分组法（以距最近月相分组，比较日均收益率）')
    print('  这是最接近 Dichev & Janes (2001) 的方法')
    print('=' * 78)

    # 计算日收益率
    daily_rets = compute_daily_returns(dates_list, prices)

    # 方案 B-1：二分法（新月附近 vs 满月附近）
    print('\n── B-1：二分法（距新月更近 vs 距满月更近）──')
    new_daily, full_daily = [], []
    for td in dates_list[1:]:
        td_dt = datetime.strptime(td, '%Y-%m-%d')
        min_new = min(abs((td_dt - datetime.strptime(d, '%Y-%m-%d')).days)
                      for d in events['new_moon'])
        min_full = min(abs((td_dt - datetime.strptime(d, '%Y-%m-%d')).days)
                       for d in events['full_moon'])
        if min_new <= min_full:
            new_daily.append(daily_rets[td])
        else:
            full_daily.append(daily_rets[td])
    print_daily_comparison(new_daily, full_daily)

    # 方案 B-2：四分法（以各月相为中心）
    print('\n── B-2：四分法（4 个月相阶段的日收益率）──')
    phase_map = assign_daily_phase_centered(dates_list, events)
    phase_daily = {0: [], 1: [], 2: [], 3: []}
    for td in dates_list[1:]:
        if td in phase_map and td in daily_rets:
            phase_daily[phase_map[td]].append(daily_rets[td])

    print(f'\n  {"阶段":<12} {"样本(天)":>8} {"日均收益":>12} {"年化":>10} {"胜率":>7}')
    print(f'  {SEP}')
    for i, name in enumerate(PHASE_NAMES_4):
        s = desc_stats(phase_daily[i])
        annual = s['mean'] * 252
        print(f'  {name:<12} {s["n"]:>8} {s["mean"]:>+11.5%} {annual:>+9.2%} {s["win_rate"]:>6.1%}')

    # 论文定义：新月半周期 = 新月附近(0) + 下弦附近(3)  ???
    # 不，论文的二分法就是距新月更近 vs 距满月更近（B-1 已经覆盖）
    # 四分法提供更细粒度的视角

    # ── 方案 B 稳定性验证 ──
    print('\n' + '=' * 78)
    print('  方案 B 稳定性验证（日收益率二分法）')
    print('=' * 78)

    print(f'\n  {"时期":<12} {"新月附近日均":>14} {"满月附近日均":>14} '
          f'{"差异":>12} {"年化差异":>10} {"p-value":>9} {"N→>F":>6}')
    print(f'  {SEP}')

    for label, start, end in SUB_PERIODS:
        sub_new_d, sub_full_d = [], []
        for td in dates_list[1:]:
            if not (start <= td <= end):
                continue
            td_dt = datetime.strptime(td, '%Y-%m-%d')
            min_new = min(abs((td_dt - datetime.strptime(d, '%Y-%m-%d')).days)
                          for d in events['new_moon'])
            min_full = min(abs((td_dt - datetime.strptime(d, '%Y-%m-%d')).days)
                           for d in events['full_moon'])
            if min_new <= min_full:
                sub_new_d.append(daily_rets[td])
            else:
                sub_full_d.append(daily_rets[td])

        sn, sf = desc_stats(sub_new_d), desc_stats(sub_full_d)
        diff = sn['mean'] - sf['mean']
        _, pval = (stats.ttest_ind(sub_new_d, sub_full_d)
                   if len(sub_new_d) > 1 and len(sub_full_d) > 1 else (0, 1))
        flag = '是' if diff > 0 else '否'
        print(f'  {label:<12} {sn["mean"]:>+13.5%} {sf["mean"]:>+13.5%} '
              f'{diff:>+11.5%} {diff * 252:>+9.2%} {pval:>9.4f} {flag:>6}')

    # ══════════════════════════════════════════════════════
    # 综合结论
    # ══════════════════════════════════════════════════════
    print('\n' + '=' * 78)
    print('  综合结论')
    print('=' * 78)

    # 方案 B 的结果作为主要结论
    sn_all = desc_stats(new_daily)
    sf_all = desc_stats(full_daily)
    diff_b = sn_all['mean'] - sf_all['mean']
    _, pval_b = stats.ttest_ind(new_daily, full_daily)
    annual_b = diff_b * 252

    # 方案 A 15 天
    nr15 = event_driven_returns(events['new_moon'], dates_set, dates_list, prices, 15)
    fr15 = event_driven_returns(events['full_moon'], dates_set, dates_list, prices, 15)
    sn_a = desc_stats(nr15)
    sf_a = desc_stats(fr15)
    diff_a = sn_a['mean'] - sf_a['mean']
    _, pval_a = stats.ttest_ind(nr15, fr15)

    print()
    print('  方案 A（事件驱动，15 天持仓，~400 独立样本）:')
    print(f'    新月后均值 {sn_a["mean"]:+.3%} vs 满月后均值 {sf_a["mean"]:+.3%}')
    print(f'    差异 {diff_a:+.3%}，p = {pval_a:.4f}')
    if diff_a > 0:
        print('    方向与论文一致（新月后更高）')
    else:
        print('    方向与论文不一致（满月后更高）')

    print()
    print('  方案 B（日收益率分组，Dichev & Janes 方法）:')
    print(f'    新月附近日均 {sn_all["mean"]:+.5%} vs 满月附近日均 {sf_all["mean"]:+.5%}')
    print(f'    差异 {diff_b:+.5%}，年化 {annual_b:+.2%}，p = {pval_b:.4f}')
    if diff_b > 0:
        print('    方向与论文一致（新月附近收益更高）')
    else:
        print('    方向与论文不一致')

    print()
    print('  学术对照:')
    print(f'    Dichev & Janes (2001): 年化差异约 +3% ~ +5%')
    print(f'    本研究 (SPY 1993-2025): 年化差异 {annual_b:+.2%}')
    if abs(annual_b) > 0 and diff_b > 0:
        print(f'    方向一致，但 p = {pval_b:.2f}，SPY 单标的 32 年数据不足以达到统计显著')
        print('    论文用 DJIA 1928-2000（72 年）+ 多国多指数，样本量大得多')
    print()
    print('  实际交易价值:')
    print(f'    年化差异 {annual_b:+.2%}，效应量 Cohen\'s d = {cohens_d(new_daily, full_daily):+.4f}')
    print('    即使效应真实存在，扣除交易成本后 alpha 极小，不具备独立交易价值')
    print('    但可作为辅助信号（与其他指标组合时提供微弱的方向性偏好）')
    print()


if __name__ == '__main__':
    main()
