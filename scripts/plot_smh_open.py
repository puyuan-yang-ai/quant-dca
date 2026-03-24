#!/usr/bin/env python3
"""
SMH 开盘价日线图
用于验证数据与网上数据是否匹配
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path

# 读取数据
data_path = Path(__file__).parent.parent / "data" / "SMH_adjusted.csv"
df = pd.read_csv(data_path, parse_dates=['datetime'])

print(f"数据范围: {df['datetime'].min()} 到 {df['datetime'].max()}")
print(f"总数据点: {len(df)}")
print(f"\n最近10条数据:")
print(df.tail(10)[['datetime', 'open', 'close']])

# 创建图表
fig, axes = plt.subplots(2, 1, figsize=(16, 10))

# 图1: 全部历史数据
ax1 = axes[0]
ax1.plot(df['datetime'], df['open'], linewidth=0.8, color='#2196F3', label='Open Price')
ax1.set_title('SMH Open Price - Full History (2000-2025)', fontsize=14, fontweight='bold')
ax1.set_xlabel('Date')
ax1.set_ylabel('Price ($)')
ax1.grid(True, alpha=0.3)
ax1.legend()
ax1.xaxis.set_major_locator(mdates.YearLocator(2))
ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))

# 图2: 最近2年数据 (更清晰查看近期走势)
recent_data = df[df['datetime'] >= '2024-01-01']
ax2 = axes[1]
ax2.plot(recent_data['datetime'], recent_data['open'], linewidth=1, color='#FF5722', label='Open Price')
ax2.set_title('SMH Open Price - Recent (2024-Present)', fontsize=14, fontweight='bold')
ax2.set_xlabel('Date')
ax2.set_ylabel('Price ($)')
ax2.grid(True, alpha=0.3)
ax2.legend()
ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)

plt.tight_layout()

# 保存图片
output_path = Path(__file__).parent.parent / "output" / "SMH_open_price_chart.png"
output_path.parent.mkdir(exist_ok=True)
plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
print(f"\n图片已保存到: {output_path}")

# 显示一些关键价格点供对比
print("\n=== 关键日期价格 (供与网上数据对比) ===")
key_dates = ['2020-01-02', '2021-01-04', '2022-01-03', '2023-01-03', '2024-01-02', '2025-01-02']
for date in key_dates:
    row = df[df['datetime'].dt.strftime('%Y-%m-%d') == date]
    if not row.empty:
        print(f"{date}: Open={row['open'].values[0]:.2f}, Close={row['close'].values[0]:.2f}")

plt.show()

