# -*- coding: utf-8 -*-
"""
盘中分钟数据拉取 + 多级别重采样（MACD 回抽零轴任务·阶段一第一步）

从 yfinance 拉取 ES=F（标普期货，近 24 小时连续）的 5 分钟 K 线（约 60 天），
再重采样为 {5,10,15,20,30,60,120} 分钟七个级别，落地到 data/intraday/。

设计要点：
  - 基础数据用 5 分钟，因 yfinance 对 5m 支持约 60 天历史；7 个目标级别都是 5m 的整数倍。
  - 时间统一转为北京时间（Asia/Shanghai, UTC+8）后落盘，便于人工对照（用户按北京时间报窗口）。
  - 重采样用 OHLCV 聚合（开=first，高=max，低=min，收=last，量=sum），并丢弃无数据的空档（周末/维护时段）。
  - 不覆盖既有日/周线 CSV：所有输出放在独立子目录 data/intraday/。

用法：
    python scripts/fetch_intraday_data.py                 # 拉 ES=F 并生成全部 7 个级别
    python scripts/fetch_intraday_data.py --ticker ES=F   # 指定标的
    python scripts/fetch_intraday_data.py --period 60d    # 指定回看天数（5m 上限约 60d）

列名格式与项目现有 CSV 一致：时间,开盘价,最高价,最低价,收盘价,成交量
（时间为北京时间，分钟级含 时:分:秒）
"""
import argparse
import os
import sys
import time
import random
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

# 用 curl_cffi 模拟浏览器指纹，降低雅虎限流概率
try:
    from curl_cffi.requests import Session as CurlSession
    _SESSION = CurlSession(impersonate="chrome")
    _USE_CURL = True
except ImportError:
    _SESSION = None
    _USE_CURL = False

_MAX_RETRIES = 4
_RETRY_BASE_WAIT = 8  # 秒

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "intraday"

BASE_INTERVAL = "5m"
BASE_MINUTES = 5
# 目标级别（分钟），均为基础 5m 的整数倍
LEVELS = [5, 10, 15, 20, 30, 60, 120]
BEIJING_TZ = "Asia/Shanghai"


def _download_with_retry(ticker: str, interval: str, period: str) -> pd.DataFrame:
    """带重试 + curl_cffi 指纹的 yf.download。"""
    kwargs = dict(interval=interval, period=period, auto_adjust=False, progress=False)
    if _USE_CURL and _SESSION is not None:
        kwargs["session"] = _SESSION

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            raw = yf.download(ticker, **kwargs)
            if not raw.empty:
                return raw
            print(f"  [retry] {ticker} 第 {attempt} 次返回空数据", file=sys.stderr)
        except Exception as e:
            print(f"  [retry] {ticker} 第 {attempt} 次失败：{e}", file=sys.stderr)
        if attempt < _MAX_RETRIES:
            wait = _RETRY_BASE_WAIT * attempt + random.uniform(1, 4)
            print(f"  [retry] 等待 {wait:.1f}s 后重试…", file=sys.stderr)
            time.sleep(wait)
    return pd.DataFrame()


def _to_ohlcv(raw: pd.DataFrame) -> pd.DataFrame:
    """整理 yfinance 返回：展平列、转北京时间索引、统一 OHLCV 列。"""
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()

    idx = pd.to_datetime(df.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    df.index = idx.tz_convert(BEIJING_TZ)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def _resample(df5: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """将 5 分钟 OHLCV 重采样为 minutes 分钟级别。"""
    if minutes == BASE_MINUTES:
        return df5.copy()

    rule = f"{minutes}min"
    agg = df5.resample(rule, label="left", closed="left").agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    })
    # 丢弃无成交（周末/维护时段产生的空档）
    agg = agg.dropna(subset=["Open", "High", "Low", "Close"])
    return agg


def _save(df: pd.DataFrame, path: Path):
    out = pd.DataFrame({
        "时间": df.index.strftime("%Y-%m-%d %H:%M:%S"),
        "开盘价": df["Open"].values,
        "最高价": df["High"].values,
        "最低价": df["Low"].values,
        "收盘价": df["Close"].values,
        "成交量": df["Volume"].fillna(0).astype("int64").values,
    })
    out.to_csv(path, index=False)
    return out


def fetch(ticker: str, period: str):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    safe = ticker.replace("=", "").replace("/", "_")  # ES=F -> ESF

    print(f"\n{'─' * 50}")
    print(f"  拉取 {ticker} {BASE_INTERVAL} 数据（period={period}）...")
    raw = _download_with_retry(ticker, interval=BASE_INTERVAL, period=period)
    if raw.empty:
        print(f"  错误：{ticker} 数据为空（重试后仍失败，未写文件）")
        return False

    df5 = _to_ohlcv(raw)
    print(f"  原始 5m：{len(df5)} 根，北京时间 {df5.index[0]} ~ {df5.index[-1]}")

    for minutes in LEVELS:
        dfl = _resample(df5, minutes)
        path = DATA_DIR / f"{safe}_{minutes}m.csv"
        _save(dfl, path)
        print(f"  [{minutes:>3}m] {len(dfl):>6} 根 -> {path.relative_to(ROOT)}")

    print(f"  完成：{ticker} 共 {len(LEVELS)} 个级别已落盘到 {DATA_DIR.relative_to(ROOT)}/")
    return True


def main():
    parser = argparse.ArgumentParser(description="拉取盘中分钟数据并多级别重采样")
    parser.add_argument("--ticker", type=str, default="ES=F", help="标的，默认 ES=F（标普期货）")
    parser.add_argument("--period", type=str, default="60d", help="回看天数，5m 上限约 60d")
    args = parser.parse_args()

    print("=" * 50)
    print("  盘中分钟数据拉取 + 多级别重采样")
    print("=" * 50)

    ok = fetch(args.ticker, args.period)

    print(f"\n{'=' * 50}")
    print("  完成！" if ok else "  失败（见上方日志）")
    print("=" * 50)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
