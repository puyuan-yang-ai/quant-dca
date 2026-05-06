"""
S&P 500 Market Breadth 预计算脚本
从 yfinance 拉取 S&P 500 成分股历史数据，计算每日"股价 > 20日SMA"的百分比，
以及连续弱势曲线（连续 N 天低于 MA20 的占比取反）。

用法：
  python scripts/fetch_breadth.py

输出：
  data/sp500_breadth.csv
  字段：date, breadth, breadth_c2, breadth_c3, breadth_c4, breadth_c5
  - breadth：站上 MA20 的比例（0-100），低值=恐慌
  - breadth_cN：100 - (连续 ≥N 天低于 MA20 的比例)，低值=恐慌
  - 排列关系：breadth ≤ breadth_c2 ≤ breadth_c3 ≤ breadth_c4 ≤ breadth_c5

已知局限：
  使用当前成分股列表回算历史数据，存在幸存者偏差。
  早期年份有效股票数较少，但百分比仍有参考价值。
"""
import os
import sys

import numpy as np
import pandas as pd
import yfinance as yf

# 项目根目录
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_FILE = os.path.join(ROOT, 'data', 'sp500_breadth.csv')

START_DATE = '1993-01-01'
SMA_WINDOW = 20


def get_sp500_tickers():
    """从 Wikipedia 获取当前 S&P 500 成分股列表"""
    import urllib.request
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    print(f"正在从 Wikipedia 获取 S&P 500 成分股列表...")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    html = urllib.request.urlopen(req).read().decode('utf-8')
    tables = pd.read_html(html)
    tickers = tables[0]['Symbol'].tolist()
    # 修正 Wikipedia 中的特殊字符（如 BRK.B → BRK-B）
    tickers = [t.replace('.', '-') for t in tickers]
    print(f"获取到 {len(tickers)} 只成分股")
    return tickers


def fetch_close_data(tickers):
    """批量拉取收盘价数据"""
    print(f"正在从 yfinance 拉取 {len(tickers)} 只股票的历史数据（{START_DATE} 至今）...")
    print("这可能需要几分钟，请耐心等待...")
    data = yf.download(tickers, start=START_DATE, group_by='ticker', auto_adjust=True)

    # 提取每只股票的 Close 列
    close_frames = {}
    for ticker in tickers:
        try:
            if ticker in data.columns.get_level_values(0):
                series = data[ticker]['Close'].dropna()
                if len(series) > SMA_WINDOW:
                    close_frames[ticker] = series
        except (KeyError, TypeError):
            continue

    close_df = pd.DataFrame(close_frames)
    print(f"成功获取 {len(close_df.columns)} 只股票的有效数据")
    return close_df


def calc_breadth(close_df):
    """计算每日 Market Breadth（站上 20 日均线的百分比）+ 连续弱势曲线"""
    sma20 = close_df.rolling(window=SMA_WINDOW).mean()
    above = (close_df > sma20).sum(axis=1)
    total = close_df.notna().sum(axis=1)
    breadth = (above / total * 100).round(2)

    # 计算连续低于 MA20 的天数计数器
    below = (close_df < sma20)  # bool DataFrame
    # 逐行累计：低于 MA20 → +1，不低于 → 归零
    consec = pd.DataFrame(0, index=close_df.index, columns=close_df.columns)
    for i in range(1, len(consec)):
        prev = consec.iloc[i - 1].values
        curr_below = below.iloc[i].values
        curr_valid = close_df.iloc[i].notna().values
        # 低于 MA20 → 前一天计数+1，否则归零；NaN 不参与
        consec.iloc[i] = np.where(curr_valid & curr_below, prev + 1, 0)

    # 对 N=2,3,4,5 计算连续弱势曲线
    consecutive_breadth = {}
    for n in [2, 3, 4, 5]:
        count_ge_n = (consec >= n).sum(axis=1)
        ratio = count_ge_n / total * 100
        # 取反：100 - 占比，使低值=恐慌
        consecutive_breadth[f'breadth_c{n}'] = (100 - ratio).round(2)

    # 去掉前 SMA_WINDOW 天（均线尚未生效）
    breadth = breadth.iloc[SMA_WINDOW:]
    for key in consecutive_breadth:
        consecutive_breadth[key] = consecutive_breadth[key].iloc[SMA_WINDOW:]

    return breadth, consecutive_breadth


def print_yearly_stats(close_df, breadth):
    """打印各年份的有效股票数和 Breadth 统计"""
    # 只用 breadth 覆盖的日期范围
    trimmed_close = close_df.loc[breadth.index]
    print(f"\n{'年份':>6}  {'有效股票数':>8}  {'Breadth均值':>10}  {'最低':>6}  {'最高':>6}")
    print("-" * 50)
    for year in sorted(breadth.index.year.unique()):
        year_breadth = breadth[breadth.index.year == year]
        year_close = trimmed_close[trimmed_close.index.year == year]
        avg_stocks = year_close.notna().sum(axis=1).mean()
        print(f"{year:>6}  {avg_stocks:>8.0f}  {year_breadth.mean():>10.1f}  "
              f"{year_breadth.min():>6.1f}  {year_breadth.max():>6.1f}")


def main():
    tickers = get_sp500_tickers()
    close_df = fetch_close_data(tickers)
    breadth, consecutive_breadth = calc_breadth(close_df)

    print_yearly_stats(close_df, breadth)

    # 保存 CSV
    result = pd.DataFrame({'date': breadth.index.strftime('%Y-%m-%d'), 'breadth': breadth.values})
    for key in ['breadth_c2', 'breadth_c3', 'breadth_c4', 'breadth_c5']:
        result[key] = consecutive_breadth[key].values
    result.to_csv(OUTPUT_FILE, index=False)
    print(f"\n已保存到 {OUTPUT_FILE}")
    print(f"共 {len(result)} 个交易日，范围 {result['date'].iloc[0]} ~ {result['date'].iloc[-1]}")
    print(f"字段：{', '.join(result.columns)}")


if __name__ == '__main__':
    main()
