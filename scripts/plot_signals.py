"""
K 线买点可视化：两套 SOTA 策略在 4 种市场环境下的买入信号对比
"""
import os
import sys
import math
import pandas as pd
import numpy as np
import mplfinance as mpf
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.data_loader import load_data
from src.indicators import calc_ema


STRATEGIES = {
    'old': {
        'label': '旧SOTA (EMA20+N5+2/5/10)',
        'ema_period': 20,
        'n_days': 5,
        'tiers': (0.02, 0.05, 0.10),
        'color': '#2ecc71',
    },
    'new': {
        'label': '新SOTA (EMA30+N7+1/3/7)',
        'ema_period': 30,
        'n_days': 7,
        'tiers': (0.01, 0.03, 0.07),
        'color': '#9b59b6',
    },
}

ENVS = {
    'bear':      {'start': '2022-01-01', 'end': '2022-12-31', 'label': 'Bear 2022'},
    'bull':      {'start': '2022-10-10', 'end': '2024-07-08', 'label': 'Bull 2022-2024'},
    'bear-bull': {'start': '2022-01-01', 'end': '2024-07-08', 'label': 'Bear-to-Bull 2022-2024'},
    'bull-bear': {'start': '2022-10-14', 'end': '2025-04-08', 'label': 'Bull-to-Bear 2022-2025'},
}

MARKET_SHARES = 0.15
LIMIT_SHARES = (0.25, 0.40, 0.70)


def compute_signals(data, ema_period, n_days, tiers):
    """Compute buy signals for a strategy, returns list of fill counts per day."""
    closes = [d['close'] for d in data]
    ema_series = calc_ema(closes, ema_period)

    consecutive_below = 0
    signals = []

    for i, day in enumerate(data):
        ema_val = ema_series[i]
        prev_close = data[i - 1]['close'] if i > 0 else day['close']

        if ema_val is not None and prev_close < ema_val:
            consecutive_below += 1
        elif ema_val is not None:
            consecutive_below = 0

        fills = 0
        if consecutive_below >= n_days:
            fills += 1  # market order always fills
            for tier in tiers:
                target = day['open'] * (1 - tier)
                if day['low'] <= target:
                    fills += 1

        signals.append(fills)

    return signals, ema_series


def build_dataframe(data):
    """Convert data list to pandas DataFrame for mplfinance."""
    df = pd.DataFrame(data)
    df['Date'] = pd.to_datetime(df['date'])
    df = df.set_index('Date')
    df = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close'})
    return df[['Open', 'High', 'Low', 'Close']]


def plot_environment(env_name, env_config, output_dir):
    """Plot candlestick chart with buy signals for one environment."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data = load_data(os.path.join(root, 'data/SOXL_adjusted.csv'),
                     env_config['start'], env_config['end'])

    df = build_dataframe(data)
    n_days = len(df)

    # Compute signals and EMA for both strategies
    strat_data = {}
    for key, strat in STRATEGIES.items():
        signals, ema_series = compute_signals(data, strat['ema_period'],
                                               strat['n_days'], strat['tiers'])
        ema_clean = [v if v is not None else np.nan for v in ema_series]
        strat_data[key] = {'signals': signals, 'ema': ema_clean}

    # Split into segments if too long
    segment_size = 130  # ~6 months of trading days
    n_segments = math.ceil(n_days / segment_size)

    fig_height = 6 * n_segments
    fig, axes = plt.subplots(n_segments, 1, figsize=(20, fig_height),
                              squeeze=False)

    for seg_idx in range(n_segments):
        start = seg_idx * segment_size
        end = min((seg_idx + 1) * segment_size, n_days)
        ax = axes[seg_idx, 0]

        seg_df = df.iloc[start:end]
        seg_dates = seg_df.index

        # Draw candlesticks manually
        for j in range(len(seg_df)):
            row = seg_df.iloc[j]
            date = seg_dates[j]
            o, h, l, c = row['Open'], row['High'], row['Low'], row['Close']

            color = '#e74c3c' if c >= o else '#27ae60'
            ax.plot([date, date], [l, h], color=color, linewidth=0.6)
            body_bottom = min(o, c)
            body_height = abs(c - o) or 0.01
            ax.bar(date, body_height, bottom=body_bottom, width=0.8,
                   color=color, edgecolor=color, linewidth=0.3)

        # Draw EMA lines
        ema20 = strat_data['old']['ema'][start:end]
        ema30 = strat_data['new']['ema'][start:end]
        ax.plot(seg_dates, ema20, color='#3498db', linewidth=1.2,
                label='EMA 20', alpha=0.8)
        ax.plot(seg_dates, ema30, color='#e67e22', linewidth=1.2,
                label='EMA 30', alpha=0.8)

        # Draw buy signals
        y_min = seg_df['Low'].min()
        y_range = seg_df['High'].max() - y_min
        offset_old = y_min - y_range * 0.06
        offset_new = y_min - y_range * 0.12

        for j in range(len(seg_df)):
            global_idx = start + j
            date = seg_dates[j]

            old_fills = strat_data['old']['signals'][global_idx]
            new_fills = strat_data['new']['signals'][global_idx]

            if old_fills > 0:
                ax.text(date, offset_old, str(old_fills),
                        ha='center', va='top', fontsize=7, fontweight='bold',
                        color=STRATEGIES['old']['color'])
            if new_fills > 0:
                ax.text(date, offset_new, str(new_fills),
                        ha='center', va='top', fontsize=7, fontweight='bold',
                        color=STRATEGIES['new']['color'])

        # Formatting
        ax.set_ylim(y_min - y_range * 0.18, seg_df['High'].max() + y_range * 0.03)
        ax.grid(True, alpha=0.2)
        ax.tick_params(axis='x', rotation=30, labelsize=8)
        ax.tick_params(axis='y', labelsize=8)

        date_range = f"{seg_dates[0].strftime('%Y-%m-%d')} ~ {seg_dates[-1].strftime('%Y-%m-%d')}"
        if n_segments > 1:
            ax.set_title(f"[{seg_idx+1}/{n_segments}] {date_range}", fontsize=10, loc='left')

    # Legend
    legend_elements = [
        Line2D([0], [0], color='#3498db', linewidth=1.5, label='EMA 20'),
        Line2D([0], [0], color='#e67e22', linewidth=1.5, label='EMA 30'),
        Line2D([0], [0], marker='$1$', color=STRATEGIES['old']['color'],
               linestyle='None', markersize=10,
               label=STRATEGIES['old']['label']),
        Line2D([0], [0], marker='$1$', color=STRATEGIES['new']['color'],
               linestyle='None', markersize=10,
               label=STRATEGIES['new']['label']),
    ]
    axes[0, 0].legend(handles=legend_elements, loc='upper left', fontsize=9,
                       framealpha=0.9)

    fig.suptitle(f"SOXL Buy Signals: {env_config['label']}", fontsize=14, y=1.0)
    plt.tight_layout()

    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, f'strategy_signals_{env_name}.png')
    fig.savefig(filepath, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"已保存: {filepath}")


if __name__ == '__main__':
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_dir = os.path.join(root, 'output')

    for env_name, env_config in ENVS.items():
        print(f"\n绘制 {env_name}...")
        plot_environment(env_name, env_config, output_dir)

    print("\n全部完成！")
