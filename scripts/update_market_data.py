"""
统一市场数据增量更新入口。

日常运行目标：
  - SPY / VIX：只下载本地最新日期之后的缺口，并带少量 overlap 覆盖最近数据修订。
  - Breadth 成员股：每只股票独立缓存，只更新缺失或落后的成员股。
  - Breadth 汇总：使用本地成员股 CSV 的计算窗口重算最近结果，保留历史汇总。

失败原则：
  Breadth 是模型特征。如果任一成员股无法补齐到 SPY 最新交易日，则退出非 0，
  由 run_daily.sh 停止当天报告并发送告警。
"""
from __future__ import annotations

import argparse
import os
import random
import sys
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

import fetch_breadth

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

SPY_FILE = DATA_DIR / "SPY_adjusted.csv"
VIX_FILE = DATA_DIR / "vix_daily.csv"
BREADTH_FILE = DATA_DIR / "sp500_breadth.csv"

SPY_FULL_START = "1993-01-01"
VIX_FULL_START = "1990-01-01"

DEFAULT_OVERLAP_DAYS = 7
DEFAULT_BREADTH_CALC_LOOKBACK_DAYS = 90
DEFAULT_BATCH_SIZE = 25
DEFAULT_BATCH_TIMEOUT = 120
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS = 10


def _load_proxy() -> str | None:
    existing = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if existing:
        return existing
    env_file = ROOT / ".env"
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

try:
    from curl_cffi.requests import Session as CurlSession

    _SESSION = CurlSession(impersonate="chrome")
except ImportError:
    _SESSION = None


def _latest_date(path: Path, date_col: str) -> date | None:
    if not path.exists():
        return None
    df = pd.read_csv(path)
    if df.empty or date_col not in df.columns:
        return None
    return pd.to_datetime(df[date_col]).dt.date.max()


def _download(ticker: str, start: str, attempts: int, backoff_seconds: int) -> pd.DataFrame:
    kwargs = {
        "start": start,
        "auto_adjust": True,
        "progress": False,
        "threads": False,
        "timeout": 30,
    }
    if _SESSION is not None:
        kwargs["session"] = _SESSION

    for attempt in range(1, attempts + 1):
        try:
            raw = yf.download(ticker, **kwargs)
            if not raw.empty:
                return raw
            print(f"  {ticker}: 第 {attempt}/{attempts} 次返回空数据", file=sys.stderr)
        except Exception as e:
            print(f"  {ticker}: 第 {attempt}/{attempts} 次失败: {e}", file=sys.stderr)

        if attempt < attempts:
            wait = backoff_seconds * (2 ** (attempt - 1)) + random.uniform(0, 2)
            print(f"  {ticker}: 等待 {wait:.1f}s 后重试", file=sys.stderr)
            time.sleep(wait)

    raise RuntimeError(f"{ticker} 下载失败")


def _flatten_yfinance(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if isinstance(raw.columns, pd.MultiIndex):
        if ticker in raw.columns.get_level_values(-1):
            raw = raw.xs(ticker, axis=1, level=-1)
        else:
            raw.columns = raw.columns.get_level_values(0)
    return raw


def _merge_on_date(path: Path, new_data: pd.DataFrame, date_col: str) -> pd.DataFrame:
    if path.exists():
        existing = pd.read_csv(path)
        combined = pd.concat([existing, new_data], ignore_index=True)
    else:
        combined = new_data

    combined[date_col] = pd.to_datetime(combined[date_col]).dt.strftime("%Y-%m-%d")
    combined = combined.drop_duplicates(subset=[date_col], keep="last").sort_values(date_col)
    combined.to_csv(path, index=False)
    return combined


def update_spy(full: bool, overlap_days: int, attempts: int, backoff_seconds: int) -> date:
    last = _latest_date(SPY_FILE, "时间")
    start = SPY_FULL_START if full or last is None else (last - timedelta(days=overlap_days)).strftime("%Y-%m-%d")
    mode = "全量" if full or last is None else f"增量(last={last}, overlap={overlap_days}d)"
    print(f"[SPY] {mode}: 从 {start} 拉取")

    raw = _flatten_yfinance(_download("SPY", start, attempts, backoff_seconds), "SPY")
    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in required if c not in raw.columns]
    if missing:
        raise RuntimeError(f"SPY 返回数据缺少字段: {missing}")

    df = pd.DataFrame({
        "时间": raw.index.strftime("%Y-%m-%d"),
        "开盘价": raw["Open"].values,
        "最高价": raw["High"].values,
        "最低价": raw["Low"].values,
        "收盘价": raw["Close"].values,
        "成交量": raw["Volume"].fillna(0).astype(int).values,
    })
    result = _merge_on_date(SPY_FILE, df, "时间")
    latest = pd.to_datetime(result["时间"]).dt.date.max()
    print(f"[SPY] 完成: {len(result)} 行，最新 {latest}")
    return latest


def update_vix(full: bool, overlap_days: int, attempts: int, backoff_seconds: int) -> date:
    last = _latest_date(VIX_FILE, "date")
    start = VIX_FULL_START if full or last is None else (last - timedelta(days=overlap_days)).strftime("%Y-%m-%d")
    mode = "全量" if full or last is None else f"增量(last={last}, overlap={overlap_days}d)"
    print(f"[VIX] {mode}: 从 {start} 拉取")

    raw = _flatten_yfinance(_download("^VIX", start, attempts, backoff_seconds), "^VIX")
    if "Close" not in raw.columns:
        raise RuntimeError("VIX 返回数据缺少 Close 字段")
    close = pd.to_numeric(raw["Close"], errors="coerce").dropna()
    df = pd.DataFrame({
        "date": close.index.strftime("%Y-%m-%d"),
        "close": close.values.round(2),
    })
    result = _merge_on_date(VIX_FILE, df, "date")
    latest = pd.to_datetime(result["date"]).dt.date.max()
    print(f"[VIX] 完成: {len(result)} 行，最新 {latest}")
    return latest


def _member_latest(ticker: str) -> date | None:
    path = fetch_breadth._member_csv_path(ticker)
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path)
    except Exception:
        return None
    if df.empty or "date" not in df.columns:
        return None
    return pd.to_datetime(df["date"]).dt.date.max()


def update_breadth(
    full: bool,
    target_latest: date,
    overlap_days: int,
    calc_lookback_days: int,
    batch_size: int,
    batch_timeout: int,
    max_attempts: int,
    backoff_seconds: int,
) -> date:
    print(f"[Breadth] 目标最新交易日: {target_latest}")
    tickers = fetch_breadth.get_sp500_tickers()

    groups: dict[str, list[str]] = defaultdict(list)
    skipped = 0
    for ticker in tickers:
        last = _member_latest(ticker)
        if full or last is None:
            groups[fetch_breadth.START_DATE].append(ticker)
        elif last < target_latest:
            start = (last - timedelta(days=overlap_days)).strftime("%Y-%m-%d")
            groups[start].append(ticker)
        else:
            skipped += 1

    to_update = sum(len(v) for v in groups.values())
    print(f"[Breadth] 成员股: {len(tickers)} 只，跳过 {skipped} 只，需更新 {to_update} 只")
    for start, group in sorted(groups.items()):
        print(f"[Breadth] 从 {start} 更新 {len(group)} 只")
        fetch_breadth.update_member_caches(
            tickers=group,
            start_date=start,
            batch_size=batch_size,
            batch_timeout=batch_timeout,
            max_attempts=max_attempts,
            backoff_seconds=backoff_seconds,
        )

    compute_start = (target_latest - timedelta(days=calc_lookback_days)).strftime("%Y-%m-%d")
    print(f"[Breadth] 本地汇总计算窗口: {compute_start} 至 {target_latest}")
    close_df = fetch_breadth.fetch_close_data(tickers, start_date=compute_start)
    actual_latest = close_df.index.max().date()
    if actual_latest < target_latest:
        raise RuntimeError(f"Breadth 成员股最新日期 {actual_latest} 落后于 SPY {target_latest}")

    breadth, consecutive_breadth = fetch_breadth.calc_breadth(close_df)
    new_result = fetch_breadth._build_result_df(breadth, consecutive_breadth)
    new_result = new_result[pd.to_datetime(new_result["date"]).dt.date <= target_latest]
    if new_result.empty or pd.to_datetime(new_result["date"]).dt.date.max() < target_latest:
        latest = None if new_result.empty else pd.to_datetime(new_result["date"]).dt.date.max()
        raise RuntimeError(f"Breadth 汇总未计算到目标日期 {target_latest}，实际 {latest}")

    existing = pd.read_csv(BREADTH_FILE) if BREADTH_FILE.exists() else pd.DataFrame()
    if not existing.empty:
        combined = pd.concat([existing, new_result], ignore_index=True)
        result = combined.drop_duplicates(subset=["date"], keep="last").sort_values("date")
    else:
        result = new_result.sort_values("date")
    result.to_csv(BREADTH_FILE, index=False)

    latest = pd.to_datetime(result["date"]).dt.date.max()
    print(f"[Breadth] 完成: {len(result)} 行，最新 {latest}")
    return latest


def main() -> int:
    parser = argparse.ArgumentParser(description="统一增量更新 SPY / VIX / S&P 500 Breadth")
    parser.add_argument("--full", action="store_true", help="全量重建 SPY/VIX 和成员股缓存")
    parser.add_argument("--overlap-days", type=int, default=DEFAULT_OVERLAP_DAYS,
                        help=f"增量下载向前覆盖的自然日，默认 {DEFAULT_OVERLAP_DAYS}")
    parser.add_argument("--breadth-calc-lookback-days", type=int, default=DEFAULT_BREADTH_CALC_LOOKBACK_DAYS,
                        help=f"Breadth 本地重算前置窗口自然日，默认 {DEFAULT_BREADTH_CALC_LOOKBACK_DAYS}")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--batch-timeout", type=int, default=DEFAULT_BATCH_TIMEOUT)
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    parser.add_argument("--backoff-seconds", type=int, default=DEFAULT_BACKOFF_SECONDS)
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    spy_latest = update_spy(args.full, args.overlap_days, args.max_attempts, args.backoff_seconds)
    vix_latest = update_vix(args.full, args.overlap_days, args.max_attempts, args.backoff_seconds)
    breadth_latest = update_breadth(
        full=args.full,
        target_latest=spy_latest,
        overlap_days=args.overlap_days,
        calc_lookback_days=args.breadth_calc_lookback_days,
        batch_size=args.batch_size,
        batch_timeout=args.batch_timeout,
        max_attempts=args.max_attempts,
        backoff_seconds=args.backoff_seconds,
    )

    if vix_latest < spy_latest:
        raise RuntimeError(f"VIX 最新日期 {vix_latest} 落后于 SPY {spy_latest}")
    if breadth_latest < spy_latest:
        raise RuntimeError(f"Breadth 最新日期 {breadth_latest} 落后于 SPY {spy_latest}")

    print("[MarketData] 全部完成")
    print(f"[MarketData] SPY={spy_latest} VIX={vix_latest} Breadth={breadth_latest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
