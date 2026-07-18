"""
情绪指标数据获取脚本
一次性拉取 VIX / Safe Haven Demand 两项数据，存为 CSV。

用法：
  python scripts/fetch_sentiment.py          # 增量更新（默认）
  python scripts/fetch_sentiment.py --full   # 全量重建

输出：
  data/vix_daily.csv    — VIX 日线（date, close）
  data/safe_haven.csv   — Safe Haven（date, spy_ret_20d, tlt_ret_20d, safe_haven）

备注：
  Put/Call Ratio (^CPCE) 已从 Yahoo Finance 下架，CBOE 也封锁直接下载，暂时跳过。
"""
import os
import sys
from datetime import date, timedelta
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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

VIX_FILE = os.path.join(ROOT, 'data', 'vix_daily.csv')
SH_FILE = os.path.join(ROOT, 'data', 'safe_haven.csv')
SPY_FILE = os.path.join(ROOT, 'data', 'SPY_adjusted.csv')

SH_ROLL_WINDOW = 20    # Safe Haven 滚动收益窗口
INCREMENTAL_LOOKBACK_DAYS = 60


def _read_existing(path: str, date_col: str = "date") -> pd.DataFrame | None:
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    if df.empty or date_col not in df.columns:
        return None
    return df


def _incremental_start(path: str, fallback: str, date_col: str = "date") -> str:
    existing = _read_existing(path, date_col=date_col)
    if existing is None:
        return fallback
    last_date = pd.to_datetime(existing[date_col].iloc[-1]).date()
    return (last_date - timedelta(days=INCREMENTAL_LOOKBACK_DAYS)).strftime("%Y-%m-%d")


def _merge_existing(path: str, new_data: pd.DataFrame, date_col: str = "date") -> pd.DataFrame:
    existing = _read_existing(path, date_col=date_col)
    if existing is None:
        return new_data.sort_values(date_col)
    combined = pd.concat([existing, new_data], ignore_index=True)
    return combined.drop_duplicates(subset=[date_col], keep="last").sort_values(date_col)


def fetch_vix(full: bool = False):
    """获取 VIX 日线数据"""
    start = '1990-01-01' if full else _incremental_start(VIX_FILE, '1990-01-01')
    print(f"正在获取 VIX (^VIX) 数据（{start} 至今）...")
    df = yf.download('^VIX', start=start, auto_adjust=True)
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
    result = _merge_existing(VIX_FILE, result) if not full else result
    result.to_csv(VIX_FILE, index=False)
    print(f"已保存到 {VIX_FILE}")
    print(f"共 {len(result)} 个交易日，范围 {result['date'].iloc[0]} ~ {result['date'].iloc[-1]}")
    print(f"VIX 均值: {result['close'].mean():.1f}, 最低: {result['close'].min():.1f}, 最高: {result['close'].max():.1f}")


def fetch_safe_haven(full: bool = False):
    """计算 Safe Haven Demand（SPY vs TLT 滚动收益差）"""
    start = '2002-01-01' if full else _incremental_start(SH_FILE, '2002-01-01')
    print(f"\n正在获取 TLT 数据（{start} 至今）...")
    tlt_df = yf.download('TLT', start=start, auto_adjust=True)
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
    result = _merge_existing(SH_FILE, result) if not full else result
    result.to_csv(SH_FILE, index=False)
    print(f"已保存到 {SH_FILE}")
    print(f"共 {len(result)} 个交易日，范围 {result['date'].iloc[0]} ~ {result['date'].iloc[-1]}")
    print(f"Safe Haven 均值: {result['safe_haven'].mean():.4f}, "
          f"最低: {result['safe_haven'].min():.4f}, 最高: {result['safe_haven'].max():.4f}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="情绪指标数据获取")
    parser.add_argument("--vix-only", action="store_true",
                        help="只拉取 VIX，跳过 Safe Haven")
    parser.add_argument("--full", action="store_true",
                        help="全量重建 VIX / Safe Haven 数据")
    args = parser.parse_args()

    print("=" * 60)
    print("  情绪指标数据获取")
    print("=" * 60)

    fetch_vix(full=args.full)

    if not args.vix_only:
        fetch_safe_haven(full=args.full)
    else:
        print("\n  --vix-only: 跳过 Safe Haven")

    print("\n" + "=" * 60)
    print("  全部完成！")
    print("=" * 60)


if __name__ == '__main__':
    main()
