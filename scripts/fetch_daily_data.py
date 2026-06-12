"""
日线数据拉取脚本
从 yfinance 拉取 SPY/SOXL/SMH 的复权日线 OHLCV 数据。

用法：
  python scripts/fetch_daily_data.py             # 拉取全部三个
  python scripts/fetch_daily_data.py --ticker SPY  # 只拉取 SPY

输出：
  data/SPY_adjusted.csv
  data/SOXL_adjusted.csv
  data/SMH_adjusted.csv

列名格式与项目现有 CSV 保持一致：时间,开盘价,最高价,最低价,收盘价,成交量
"""
import argparse
import os
from pathlib import Path

import pandas as pd
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


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

TICKERS = {
    "SPY":  {"start": "1993-01-01", "file": "SPY_adjusted.csv"},
    "SOXL": {"start": "2010-03-01", "file": "SOXL_adjusted.csv"},
    "SMH":  {"start": "2000-01-01", "file": "SMH_adjusted.csv"},
}


def fetch_ticker(ticker: str):
    cfg = TICKERS[ticker]
    output_path = DATA_DIR / cfg["file"]
    print(f"\n{'─'*50}")
    print(f"  拉取 {ticker} 日线数据（{cfg['start']} 至今）...")

    raw = yf.download(ticker, start=cfg["start"], auto_adjust=True)
    if raw.empty:
        print(f"  错误：{ticker} 数据为空")
        return

    # yfinance returns MultiIndex columns like ('Close', 'SPY'); flatten them
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    df = pd.DataFrame({
        "时间": raw.index.strftime("%Y-%m-%d"),
        "开盘价": raw["Open"].values,
        "最高价": raw["High"].values,
        "最低价": raw["Low"].values,
        "收盘价": raw["Close"].values,
        "成交量": raw["Volume"].astype(int).values,
    })

    df.to_csv(output_path, index=False)
    print(f"  已保存到 {output_path}")
    print(f"  共 {len(df)} 个交易日，范围 {df['时间'].iloc[0]} ~ {df['时间'].iloc[-1]}")


def main():
    parser = argparse.ArgumentParser(description="拉取 SPY/SOXL/SMH 日线数据")
    parser.add_argument("--ticker", type=str, default=None,
                        choices=list(TICKERS.keys()),
                        help="只拉取指定标的（不指定则全部拉取）")
    args = parser.parse_args()

    print("=" * 50)
    print("  日线数据拉取")
    print("=" * 50)

    targets = [args.ticker] if args.ticker else list(TICKERS.keys())
    for t in targets:
        fetch_ticker(t)

    print(f"\n{'='*50}")
    print("  全部完成！")
    print("=" * 50)


if __name__ == "__main__":
    main()
