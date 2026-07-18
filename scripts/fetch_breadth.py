"""
S&P 500 Market Breadth 预计算脚本
从 yfinance 拉取 S&P 500 成分股历史数据，计算每日"股价 > 20日SMA"的百分比，
以及连续弱势曲线（连续 N 天低于 MA20 的占比取反）。

用法：
  python scripts/fetch_breadth.py
  python scripts/fetch_breadth.py --batch-size 25 --batch-timeout 120

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
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
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

# 项目根目录
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_FILE = os.path.join(ROOT, 'data', 'sp500_breadth.csv')
MEMBER_DIR = Path(ROOT) / 'data' / 'breadth_members'

START_DATE = '1993-01-01'
SMA_WINDOW = 20

# 增量更新时，向前多拉这么多个自然日作为前置窗口，
# 以保证 MA20 与连续低于 MA20 的计数器在新日期上收敛到正确值。
INCREMENTAL_LOOKBACK_DAYS = 60
DEFAULT_BATCH_SIZE = 25
DEFAULT_BATCH_TIMEOUT = 120
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS = 10

YFINANCE_CACHE_DIR = Path(ROOT) / "tmp" / "yfinance-cache"
YFINANCE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
try:
    yf.set_tz_cache_location(str(YFINANCE_CACHE_DIR))
except Exception as e:
    print(f"警告：设置 yfinance cache 目录失败：{e}", file=sys.stderr)


def get_sp500_tickers():
    """获取当前 S&P 500 成分股列表（Wikipedia 优先，GitHub 备用）"""
    from io import StringIO

    # 数据源 1: Wikipedia
    wiki_url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    print("正在获取 S&P 500 成分股列表...")
    try:
        resp = requests.get(wiki_url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        }, timeout=30)
        resp.raise_for_status()
        tables = pd.read_html(StringIO(resp.text))
        tickers = tables[0]['Symbol'].tolist()
        tickers = [t.replace('.', '-') for t in tickers]
        print(f"  (Wikipedia) 获取到 {len(tickers)} 只成分股")
        return tickers
    except Exception as e:
        print(f"  Wikipedia 不可用 ({e})，切换到 GitHub 备用源...")

    # 数据源 2: GitHub datasets/s-and-p-500-companies
    gh_url = 'https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv'
    resp = requests.get(gh_url, timeout=15)
    resp.raise_for_status()
    df = pd.read_csv(StringIO(resp.text))
    tickers = df['Symbol'].tolist()
    tickers = [t.replace('.', '-') for t in tickers]
    print(f"  (GitHub) 获取到 {len(tickers)} 只成分股")
    return tickers


def fetch_close_data(tickers, start_date=START_DATE):
    """从本地成员股缓存加载收盘价矩阵。"""
    close_frames = {}
    missing = []
    stale = []

    for ticker in tickers:
        path = _member_csv_path(ticker)
        if not path.exists():
            missing.append(ticker)
            continue
        df = pd.read_csv(path, parse_dates=['date'])
        df = df[df['date'] >= pd.to_datetime(start_date)]
        if len(df) <= SMA_WINDOW:
            missing.append(ticker)
            continue
        close_frames[ticker] = df.set_index('date')['close'].sort_index()

    if missing:
        raise RuntimeError(
            f"成员股缓存不完整，缺少/不足 {len(missing)} 只: {missing[:20]}"
        )

    close_df = pd.DataFrame(close_frames).sort_index()
    if close_df.empty:
        raise RuntimeError("成员股缓存为空，无法计算 Breadth")

    target_latest = close_df.index.max()
    for ticker, series in close_frames.items():
        if series.dropna().empty or series.dropna().index.max() < target_latest:
            stale.append(ticker)
    if stale:
        raise RuntimeError(
            f"成员股缓存未全部更新到 {target_latest.date()}，落后 {len(stale)} 只: {stale[:20]}"
        )

    print(f"成功加载 {len(close_df.columns)} 只成员股缓存，最新日期 {target_latest.date()}")
    return close_df


def _safe_ticker_name(ticker: str) -> str:
    return ticker.replace('/', '-').replace(':', '-')


def _member_csv_path(ticker: str) -> Path:
    return MEMBER_DIR / f"{_safe_ticker_name(ticker)}.csv"


def _normalize_download(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        if ticker in raw.columns.get_level_values(0):
            raw = raw[ticker]
        else:
            raw.columns = raw.columns.get_level_values(0)
    raw = raw.reset_index()
    raw.columns = [str(c).lower() for c in raw.columns]
    for candidate in ('date', 'datetime', 'index'):
        if candidate in raw.columns:
            raw = raw.rename(columns={candidate: 'date'})
            break
    if 'date' not in raw.columns or 'close' not in raw.columns:
        return pd.DataFrame()
    result = raw[['date', 'close']].copy()
    result['date'] = pd.to_datetime(result['date']).dt.normalize()
    result['close'] = pd.to_numeric(result['close'], errors='coerce')
    return result.dropna(subset=['date', 'close'])


def _merge_member_cache(ticker: str, new_data: pd.DataFrame) -> None:
    path = _member_csv_path(ticker)
    if new_data.empty:
        raise RuntimeError(f"{ticker} 下载结果为空")
    if path.exists():
        existing = pd.read_csv(path, parse_dates=['date'])
        combined = pd.concat([existing, new_data], ignore_index=True)
        combined = combined.drop_duplicates(subset=['date'], keep='last').sort_values('date')
    else:
        combined = new_data.sort_values('date')
    combined.to_csv(path, index=False)


def fetch_batch_child(tickers_path: str, start_date: str) -> int:
    """子进程入口：更新一个 batch 的成员股缓存。"""
    MEMBER_DIR.mkdir(parents=True, exist_ok=True)
    tickers = json.loads(Path(tickers_path).read_text())
    failed = []

    for ticker in tickers:
        try:
            raw = yf.download(
                ticker,
                start=start_date,
                auto_adjust=True,
                progress=False,
                threads=False,
                timeout=20,
            )
            df = _normalize_download(raw, ticker)
            _merge_member_cache(ticker, df)
            print(f"  {ticker}: {len(df)} rows")
        except Exception as e:
            failed.append((ticker, str(e)))
            print(f"  {ticker}: 失败: {e}", file=sys.stderr)

    if failed:
        print(f"batch 失败 {len(failed)} 只: {failed[:10]}", file=sys.stderr)
        return 1
    return 0


def _run_batch_with_retry(
    batch_id: int,
    tickers: list[str],
    start_date: str,
    batch_timeout: int,
    max_attempts: int,
    backoff_seconds: int,
) -> None:
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
        json.dump(tickers, f)
        tickers_path = f.name

    try:
        for attempt in range(1, max_attempts + 1):
            print(f"批次 {batch_id}: {len(tickers)} 只，第 {attempt}/{max_attempts} 次尝试")
            cmd = [
                sys.executable,
                __file__,
                '--fetch-batch',
                tickers_path,
                '--start-date',
                start_date,
            ]
            try:
                result = subprocess.run(
                    cmd,
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                    timeout=batch_timeout,
                )
            except subprocess.TimeoutExpired:
                result = None
                print(f"批次 {batch_id}: 超时 {batch_timeout}s", file=sys.stderr)

            if result is not None:
                if result.stdout:
                    print(result.stdout, end='')
                if result.stderr:
                    print(result.stderr, end='', file=sys.stderr)
                if result.returncode == 0:
                    print(f"批次 {batch_id}: 成功")
                    return

            if attempt < max_attempts:
                wait = backoff_seconds * (2 ** (attempt - 1))
                print(f"批次 {batch_id}: 失败，等待 {wait}s 后重试")
                time.sleep(wait)

        raise RuntimeError(f"批次 {batch_id} 最终失败: {tickers}")
    finally:
        try:
            os.unlink(tickers_path)
        except OSError:
            pass


def update_member_caches(
    tickers: list[str],
    start_date: str,
    batch_size: int,
    batch_timeout: int,
    max_attempts: int,
    backoff_seconds: int,
) -> None:
    print(
        f"更新成员股缓存：{len(tickers)} 只，batch_size={batch_size}, "
        f"timeout={batch_timeout}s, attempts={max_attempts}"
    )
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        _run_batch_with_retry(
            batch_id=i // batch_size + 1,
            tickers=batch,
            start_date=start_date,
            batch_timeout=batch_timeout,
            max_attempts=max_attempts,
            backoff_seconds=backoff_seconds,
        )


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


def _build_result_df(breadth, consecutive_breadth) -> pd.DataFrame:
    """把 breadth 计算结果拼成标准输出 DataFrame（date 为字符串）。"""
    result = pd.DataFrame({'date': breadth.index.strftime('%Y-%m-%d'), 'breadth': breadth.values})
    for key in ['breadth_c2', 'breadth_c3', 'breadth_c4', 'breadth_c5']:
        result[key] = consecutive_breadth[key].values
    return result


def main():
    parser = argparse.ArgumentParser(description="增量更新 S&P 500 Breadth")
    parser.add_argument("--full", action="store_true", help="全量重建成员股缓存和 Breadth")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
                        help=f"成员股下载批大小，默认 {DEFAULT_BATCH_SIZE}")
    parser.add_argument("--batch-timeout", type=int, default=DEFAULT_BATCH_TIMEOUT,
                        help=f"每个批次子进程硬超时秒数，默认 {DEFAULT_BATCH_TIMEOUT}")
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS,
                        help=f"每个批次最大尝试次数，默认 {DEFAULT_MAX_ATTEMPTS}")
    parser.add_argument("--backoff-seconds", type=int, default=DEFAULT_BACKOFF_SECONDS,
                        help=f"指数退避初始秒数，默认 {DEFAULT_BACKOFF_SECONDS}")
    parser.add_argument("--fetch-batch", type=str, default=None,
                        help=argparse.SUPPRESS)
    parser.add_argument("--start-date", type=str, default=None,
                        help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.fetch_batch:
        sys.exit(fetch_batch_child(args.fetch_batch, args.start_date or START_DATE))

    existing = None
    start_date = START_DATE
    if not args.full and os.path.exists(OUTPUT_FILE):
        existing = pd.read_csv(OUTPUT_FILE)
        if not existing.empty:
            last_date = pd.to_datetime(existing['date'].iloc[-1]).date()
            if last_date >= date.today():
                print(f"数据已是最新（{last_date}），无需更新。")
                return
            # 前置窗口：往前多拉若干天，保证 MA20 / 连续计数收敛
            start_date = (last_date - timedelta(days=INCREMENTAL_LOOKBACK_DAYS)).strftime('%Y-%m-%d')
            print(f"增量更新模式：现有数据截至 {last_date}，从 {start_date} 起拉取前置窗口。")
    else:
        print("全量模式：从 1993 年起重算全部历史。")

    tickers = get_sp500_tickers()
    update_member_caches(
        tickers=tickers,
        start_date=start_date,
        batch_size=args.batch_size,
        batch_timeout=args.batch_timeout,
        max_attempts=args.max_attempts,
        backoff_seconds=args.backoff_seconds,
    )
    close_df = fetch_close_data(tickers, start_date=start_date)
    breadth, consecutive_breadth = calc_breadth(close_df)
    new_result = _build_result_df(breadth, consecutive_breadth)

    if existing is not None:
        # 用新算的值覆盖重叠日期，并追加新日期；旧的非重叠历史原样保留
        combined = pd.concat([existing, new_result], ignore_index=True)
        combined = combined.drop_duplicates(subset=['date'], keep='last').sort_values('date')
        added = len(combined) - len(existing)
        result = combined
        print(f"\n增量合并完成：新增/覆盖后总计 {len(result)} 行（净新增约 {added} 行）。")
    else:
        result = new_result
        print_yearly_stats(close_df, breadth)

    result.to_csv(OUTPUT_FILE, index=False)
    print(f"已保存到 {OUTPUT_FILE}")
    print(f"共 {len(result)} 个交易日，范围 {result['date'].iloc[0]} ~ {result['date'].iloc[-1]}")
    print(f"字段：{', '.join(result.columns)}")


if __name__ == '__main__':
    main()
