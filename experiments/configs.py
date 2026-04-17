"""
实验参数配置
定义所有市场环境和各阶段的实验组合
"""
from src.modules.tiers import FixedTiers, VolatilityTiers
from src.modules.entry import UnconditionalEntry, EMAFilterEntry, NDayConfirmEntry
from src.modules.position import FixedPyramid, AdaptivePyramid, DowntrendOnly
from src.modules.take_profit import (
    NoTakeProfit, DeviationPeakTP, TrendConfirmTP, DualTakeProfit
)

# ── 市场环境 ──────────────────────────────────────────────

MARKET_ENVS = {
    'bear':      {'start': '2022-01-01', 'end': '2022-12-31', 'weight': 0.15, 'label': '纯熊市'},
    'bull':      {'start': '2022-10-10', 'end': '2024-07-08', 'weight': 0.15, 'label': '纯牛市'},
    'bear-bull': {'start': '2022-01-01', 'end': '2024-07-08', 'weight': 0.35, 'label': '熊转牛'},
    'bull-bear': {'start': '2022-10-14', 'end': '2025-04-08', 'weight': 0.35, 'label': '牛转熊'},
}

DATA_FILE = 'data/SOXL_adjusted.csv'
SMH_FILE = 'data/SMH_adjusted.csv'
FEE_RATE = 0.01

# ── 默认模块（baseline 配置） ──────────────────────────────

DEFAULT_TIERS = FixedTiers(drops=(0.02, 0.05, 0.10))
DEFAULT_ENTRY = UnconditionalEntry()
DEFAULT_POSITION = FixedPyramid(market_shares=0.70, limit_shares=(0.40, 0.25, 0.15))
DEFAULT_TP = NoTakeProfit()


# ── 第一阶段：档口设置 ──────────────────────────────────────

STAGE_1 = {
    '1-A': {
        'label': 'Baseline 固定比例 2%/5%/10%',
        'tiers': DEFAULT_TIERS,
        'entry': DEFAULT_ENTRY,
        'position': DEFAULT_POSITION,
        'take_profit': DEFAULT_TP,
    },
    '1-B': {
        'label': '波动率动态档口',
        'tiers': VolatilityTiers(lookback=14, percentiles=(30, 60), max_scale=0.90),
        'entry': DEFAULT_ENTRY,
        'position': DEFAULT_POSITION,
        'take_profit': DEFAULT_TP,
    },
    '1-C': {
        'label': '波动率动态（无市价单）',
        'tiers': VolatilityTiers(lookback=14, percentiles=(30, 60), max_scale=0.90),
        'entry': DEFAULT_ENTRY,
        'position': FixedPyramid(market_shares=0, limit_shares=(0.40, 0.25, 0.15)),
        'take_profit': DEFAULT_TP,
    },
}


def build_stage_2(best_tiers):
    """构建第二阶段实验配置（锁定最优档口）"""
    return {
        '2-A': {
            'label': '无条件每日买入',
            'tiers': best_tiers,
            'entry': UnconditionalEntry(),
            'position': DEFAULT_POSITION,
            'take_profit': DEFAULT_TP,
        },
        '2-B': {
            'label': 'EMA 过滤',
            'tiers': best_tiers,
            'entry': EMAFilterEntry(),
            'position': DEFAULT_POSITION,
            'take_profit': DEFAULT_TP,
        },
        '2-C-2': {
            'label': '连续 2 天确认',
            'tiers': best_tiers,
            'entry': NDayConfirmEntry(n_days=2),
            'position': DEFAULT_POSITION,
            'take_profit': DEFAULT_TP,
        },
        '2-C-3': {
            'label': '连续 3 天确认',
            'tiers': best_tiers,
            'entry': NDayConfirmEntry(n_days=3),
            'position': DEFAULT_POSITION,
            'take_profit': DEFAULT_TP,
        },
        '2-C-4': {
            'label': '连续 4 天确认',
            'tiers': best_tiers,
            'entry': NDayConfirmEntry(n_days=4),
            'position': DEFAULT_POSITION,
            'take_profit': DEFAULT_TP,
        },
    }


def build_stage_3(best_tiers, best_entry):
    """构建第三阶段实验配置（锁定最优档口 + 入场）"""
    return {
        '3-A': {
            'label': '固定倒金字塔',
            'tiers': best_tiers,
            'entry': best_entry,
            'position': FixedPyramid(),
            'take_profit': DEFAULT_TP,
        },
        '3-B': {
            'label': '自适应金字塔',
            'tiers': best_tiers,
            'entry': best_entry,
            'position': AdaptivePyramid(),
            'take_profit': DEFAULT_TP,
        },
        '3-C': {
            'label': '仅下跌买入',
            'tiers': best_tiers,
            'entry': best_entry,
            'position': DowntrendOnly(),
            'take_profit': DEFAULT_TP,
        },
    }


def build_stage_4(best_tiers, best_entry, best_position):
    """构建第四阶段实验配置（锁定最优档口 + 入场 + 仓位）"""
    return {
        '4-0': {
            'label': '无止盈（对照）',
            'tiers': best_tiers,
            'entry': best_entry,
            'position': best_position,
            'take_profit': NoTakeProfit(),
        },
        '4-A': {
            'label': '偏离度峰值止盈',
            'tiers': best_tiers,
            'entry': best_entry,
            'position': best_position,
            'take_profit': DeviationPeakTP(sell_pct=0.50),
        },
        '4-B': {
            'label': '趋势确认止盈',
            'tiers': best_tiers,
            'entry': best_entry,
            'position': best_position,
            'take_profit': TrendConfirmTP(n_days=3, sell_pct=0.25),
        },
        '4-AB': {
            'label': '双层止盈',
            'tiers': best_tiers,
            'entry': best_entry,
            'position': best_position,
            'take_profit': DualTakeProfit(
                DeviationPeakTP(sell_pct=0.50),
                TrendConfirmTP(n_days=3, sell_pct=0.25),
            ),
        },
    }
