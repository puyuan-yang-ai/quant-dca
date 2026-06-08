"""
周线数据拉取脚本
从 yfinance 拉取 SPY/SMH 周线 OHLC 和 S&P 500 周线 Breadth 数据。

用法：
  python scripts/fetch_weekly_data.py

输出：
  data/SPY_weekly.csv（date, open, high, low, close）
  data/SMH_weekly.csv（date, open, high, low, close）
  data/sp500_breadth_weekly.csv（date, breadth）
"""
import os
import sys
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf


def _load_proxy() -> str | None:
    existing = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if existing:
        return existing
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("YAHOO_PROXY="):
                return line.split("=", 1)[1].strip()
    return None

_PROXY = _load_proxy()
if _PROXY:
    os.environ.setdefault("HTTPS_PROXY", _PROXY)
    os.environ.setdefault("HTTP_PROXY", _PROXY)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

START_DATE = '1993-01-01'
# Breadth 从更早开始以确保 20 周 SMA 预热充分（回测只用 2022 起）
BREADTH_START_DATE = '2020-01-01'
SMA_WINDOW = 20  # 20 周 SMA


def fetch_weekly_ohlc(ticker, output_path):
    """拉取单只标的的周线 OHLC 数据"""
    print(f"正在拉取 {ticker} 周线数据...")
    df = yf.download(ticker, start=START_DATE, interval='1wk', auto_adjust=True)

    # 统一列名
    df = df.reset_index()
    # yfinance 返回的列可能是 MultiIndex，处理一下
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] if col[1] == '' or col[1] == ticker else col[0]
                      for col in df.columns]

    df = df.rename(columns={
        'Date': '时间', 'Open': '开盘价', 'High': '最高价',
        'Low': '最低价', 'Close': '收盘价',
    })
    df['时间'] = pd.to_datetime(df['时间']).dt.strftime('%Y-%m-%d')
    df = df[['时间', '开盘价', '最高价', '最低价', '收盘价']]

    df.to_csv(output_path, index=False)
    print(f"  已保存到 {output_path}（{len(df)} 周）")
    return df


def get_sp500_tickers():
    """从 Wikipedia 获取当前 S&P 500 成分股列表"""
    from io import StringIO
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    print("正在从 Wikipedia 获取 S&P 500 成分股列表...")
    # Wikipedia 封禁了代理数据中心 IP，直连即可（Wikipedia 在国内可正常访问）
    resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
    resp.raise_for_status()
    tables = pd.read_html(StringIO(resp.text))
    tickers = tables[0]['Symbol'].tolist()
    tickers = [t.replace('.', '-') for t in tickers]
    print(f"获取到 {len(tickers)} 只成分股")
    return tickers


def fetch_weekly_breadth(tickers, output_path):
    """
    拉取 S&P 500 成分股日线数据，计算 20 周 SMA Breadth，重采样为周频。

    策略：用日线数据计算（避免 yfinance 周线数据的 NaN 对齐问题），
    20 周 SMA ≈ 100 交易日 SMA，然后取每周五的值作为该周的 Breadth。
    """
    SMA_DAYS = 100  # 20 周 ≈ 100 个交易日

    import time

    print(f"正在分批拉取 {len(tickers)} 只成分股的日线数据（{BREADTH_START_DATE} 起）...")
    print("这可能需要几分钟，请耐心等待...")

    batch_size = 50
    close_frames = {}
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(tickers) - 1) // batch_size + 1
        print(f"  批次 {batch_num}/{total_batches}（{len(batch)} 只）...")

        try:
            data = yf.download(batch, start=BREADTH_START_DATE,
                               group_by='ticker', auto_adjust=True)
            if len(batch) == 1:
                s = data['Close'].dropna()
                if len(s) > SMA_DAYS:
                    close_frames[batch[0]] = s
            else:
                for t in batch:
                    try:
                        if t in data.columns.get_level_values(0):
                            s = data[t]['Close']
                            if isinstance(s, pd.DataFrame):
                                s = s.iloc[:, 0]
                            s = s.dropna()
                            if len(s) > SMA_DAYS:
                                close_frames[t] = s
                    except (KeyError, TypeError):
                        continue
        except Exception as e:
            print(f"    批次下载失败: {e}")
        time.sleep(2)

    close_df = pd.DataFrame(close_frames)
    print(f"成功获取 {len(close_df.columns)} 只股票的有效日线数据")

    # 用 100 日 SMA（≈20 周 SMA）计算每日 Breadth
    sma = close_df.rolling(window=SMA_DAYS).mean()
    above = (close_df > sma).sum(axis=1)
    total = close_df.notna().sum(axis=1)
    daily_breadth = (above / total * 100).round(2)

    # 去掉前 SMA_DAYS 天
    daily_breadth = daily_breadth.iloc[SMA_DAYS:]

    # 重采样为周频（取每周最后一个交易日的值）
    breadth = daily_breadth.resample('W-MON').last().dropna()

    # 打印统计
    n_stocks = len(close_df.columns)
    print(f"\n{'年份':>6}  {'Breadth均值':>10}  {'最低':>6}  {'最高':>6}  {'周数':>4}")
    print("-" * 45)
    for year in sorted(breadth.index.year.unique()):
        yb = breadth[breadth.index.year == year]
        print(f"{year:>6}  {yb.mean():>10.1f}  {yb.min():>6.1f}  {yb.max():>6.1f}  {len(yb):>4}")
    print(f"\n成分股数: {n_stocks}")

    # 保存 CSV
    result = pd.DataFrame({
        'date': breadth.index.strftime('%Y-%m-%d'),
        'breadth': breadth.values,
    })
    result.to_csv(output_path, index=False)
    print(f"\n已保存到 {output_path}（{len(result)} 周）")


def main():
    spy_path = os.path.join(ROOT, 'data', 'SPY_weekly.csv')
    smh_path = os.path.join(ROOT, 'data', 'SMH_weekly.csv')
    breadth_path = os.path.join(ROOT, 'data', 'sp500_breadth_weekly.csv')

    # SPY/SMH 周线如已存在则跳过
    if not os.path.exists(spy_path):
        fetch_weekly_ohlc('SPY', spy_path)
    else:
        print(f"SPY 周线数据已存在，跳过: {spy_path}")

    if not os.path.exists(smh_path):
        fetch_weekly_ohlc('SMH', smh_path)
    else:
        print(f"SMH 周线数据已存在，跳过: {smh_path}")

    tickers = get_sp500_tickers()
    fetch_weekly_breadth(tickers, breadth_path)

    print("\n全部完成！")


if __name__ == '__main__':
    main()
