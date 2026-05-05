"""
情绪指标数据获取脚本
一次性拉取 VIX / Safe Haven Demand 两项数据，存为 CSV。

用法：
  python scripts/fetch_sentiment.py

输出：
  data/vix_daily.csv    — VIX 日线（date, close）
  data/safe_haven.csv   — Safe Haven（date, spy_ret_20d, tlt_ret_20d, safe_haven）

备注：
  Put/Call Ratio (^CPCE) 已从 Yahoo Finance 下架，CBOE 也封锁直接下载，暂时跳过。
"""
import os
import sys

import pandas as pd
import yfinance as yf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

VIX_FILE = os.path.join(ROOT, 'data', 'vix_daily.csv')
SH_FILE = os.path.join(ROOT, 'data', 'safe_haven.csv')
SPY_FILE = os.path.join(ROOT, 'data', 'SPY_adjusted.csv')

SH_ROLL_WINDOW = 20    # Safe Haven 滚动收益窗口


def fetch_vix():
    """获取 VIX 日线数据"""
    print("正在获取 VIX (^VIX) 数据...")
    df = yf.download('^VIX', start='1990-01-01', auto_adjust=True)
    if df.empty:
        print("错误：VIX 数据为空")
        return

    close = df['Close'].dropna()
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    result = pd.DataFrame({
        'date': close.index.strftime('%Y-%m-%d'),
        'close': close.values.round(2),
    })
    result.to_csv(VIX_FILE, index=False)
    print(f"已保存到 {VIX_FILE}")
    print(f"共 {len(result)} 个交易日，范围 {result['date'].iloc[0]} ~ {result['date'].iloc[-1]}")
    print(f"VIX 均值: {result['close'].mean():.1f}, 最低: {result['close'].min():.1f}, 最高: {result['close'].max():.1f}")


def fetch_safe_haven():
    """计算 Safe Haven Demand（SPY vs TLT 滚动收益差）"""
    print("\n正在获取 TLT 数据...")
    tlt_df = yf.download('TLT', start='2002-01-01', auto_adjust=True)
    if tlt_df.empty:
        print("错误：TLT 数据为空")
        return

    tlt_close = tlt_df['Close'].dropna()
    if isinstance(tlt_close, pd.DataFrame):
        tlt_close = tlt_close.iloc[:, 0]

    # 加载本地 SPY 数据（中文列名：时间,开盘价,最高价,最低价,收盘价,成交量）
    print("正在加载本地 SPY 数据...")
    spy_csv = pd.read_csv(SPY_FILE)
    spy_csv['时间'] = pd.to_datetime(spy_csv['时间'])
    spy_close = spy_csv.set_index('时间')['收盘价']

    # 对齐日期范围
    common_start = max(spy_close.index.min(), tlt_close.index.min())
    common_end = min(spy_close.index.max(), tlt_close.index.max())
    spy_close = spy_close.loc[common_start:common_end]
    tlt_close = tlt_close.loc[common_start:common_end]

    # 取交集日期
    common_dates = spy_close.index.intersection(tlt_close.index)
    spy_close = spy_close.loc[common_dates]
    tlt_close = tlt_close.loc[common_dates]

    # 计算 20 日滚动收益率
    spy_ret = spy_close.pct_change(SH_ROLL_WINDOW)
    tlt_ret = tlt_close.pct_change(SH_ROLL_WINDOW)

    # Safe Haven = TLT 收益 - SPY 收益（正值 = 避险情绪）
    safe_haven = tlt_ret - spy_ret

    # 去掉前 N 天
    valid = safe_haven.dropna()
    spy_ret_valid = spy_ret.loc[valid.index]
    tlt_ret_valid = tlt_ret.loc[valid.index]

    result = pd.DataFrame({
        'date': valid.index.strftime('%Y-%m-%d'),
        'spy_ret_20d': spy_ret_valid.values.round(6),
        'tlt_ret_20d': tlt_ret_valid.values.round(6),
        'safe_haven': valid.values.round(6),
    })
    result.to_csv(SH_FILE, index=False)
    print(f"已保存到 {SH_FILE}")
    print(f"共 {len(result)} 个交易日，范围 {result['date'].iloc[0]} ~ {result['date'].iloc[-1]}")
    print(f"Safe Haven 均值: {result['safe_haven'].mean():.4f}, "
          f"最低: {result['safe_haven'].min():.4f}, 最高: {result['safe_haven'].max():.4f}")


def main():
    print("=" * 60)
    print("  情绪指标数据获取")
    print("=" * 60)

    fetch_vix()
    fetch_safe_haven()

    print("\n" + "=" * 60)
    print("  全部完成！")
    print("=" * 60)


if __name__ == '__main__':
    main()
