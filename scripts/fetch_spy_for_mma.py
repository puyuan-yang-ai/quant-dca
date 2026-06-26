"""拉取 SPY 真实行情（yfinance）并按 ratio 换算为 ESM 等价位，增量维护 data/spy_daily.csv，供 MMA 周报校验使用。"""
import argparse
import os
import sys
import time
import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

# ratio = MMA 周报当周高点 ESM ÷ 同日 SPY 高点。每月 1 日重新校准。
ESM_SPY_RATIO = 10.06
RATIO_LAST_UPDATED = "2026-05-18"
RATIO_CONTRACT = "ESM26 (June 2026 e-mini)"

# ── SOCKS5 代理配置 ──────────────────────────────────────────────────────────
# 走新加坡 ECS 出口，绕过雅虎对本机 IP 的限流。
# 优先级：已有环境变量 > .env 文件 > 无代理（直连）
def _load_proxy() -> str | None:
    """从 .env 文件或环境变量读取代理地址，不在代码里硬编码密码。"""
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

# 用 curl_cffi 模拟浏览器指纹，大幅降低雅虎限流概率
try:
    from curl_cffi.requests import Session as CurlSession
    _SESSION = CurlSession(impersonate="chrome")
    _USE_CURL = True
except ImportError:
    _SESSION = None
    _USE_CURL = False

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "spy_daily.csv"
SPY_TICKER = "SPY"

# 每次运行都强制重新拉取最近这么多个交易日的数据，覆盖掉本地可能不完整的记录
REFRESH_TRADING_DAYS = 3

_MAX_RETRIES = 3
_RETRY_BASE_WAIT = 8  # 秒


def _download_with_retry(ticker: str, start: str, end: str) -> pd.DataFrame:
    """带重试的 yf.download，优先使用 curl_cffi session 模拟浏览器指纹。"""
    kwargs = dict(start=start, end=end, auto_adjust=False, progress=False)
    if _USE_CURL and _SESSION is not None:
        kwargs["session"] = _SESSION

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            raw = yf.download(ticker, **kwargs)
            if not raw.empty:
                return raw
            print(f"[fetch] 第 {attempt} 次尝试返回空数据", file=sys.stderr)
        except Exception as e:
            print(f"[fetch] 第 {attempt} 次尝试失败：{e}", file=sys.stderr)

        if attempt < _MAX_RETRIES:
            wait = _RETRY_BASE_WAIT * attempt + random.uniform(1, 4)
            print(f"[fetch] 等待 {wait:.1f}s 后重试…", file=sys.stderr)
            time.sleep(wait)

    return pd.DataFrame()


def _trading_days_start(n: int) -> date:
    """往前推 n 个交易日的起始日期（按自然日 * 2 保守估算，涵盖周末/假日）。"""
    return date.today() - timedelta(days=n * 2 + 3)


def fetch_spy(days: int) -> pd.DataFrame:
    """拉取 SPY 日线数据，增量维护本地缓存。
    策略：每次都强制重新拉取最近 REFRESH_TRADING_DAYS 个交易日并覆盖缓存中同日行，
    避免缓存里存有盘中或假期低流动性的不完整记录；更早的历史保持不变。
    """
    today = date.today()

    if CSV_PATH.exists():
        existing = pd.read_csv(CSV_PATH, parse_dates=["date"])
        existing["date"] = existing["date"].dt.normalize()
    else:
        existing = None

    refresh_start = _trading_days_start(REFRESH_TRADING_DAYS)

    if existing is not None:
        last_date = existing["date"].max().date()
        start = min(
            refresh_start,
            last_date + timedelta(days=1) if last_date < refresh_start else refresh_start,
        )
    else:
        start = today - timedelta(days=days * 2 + 10)

    end = today + timedelta(days=1)  # yfinance end 是开区间

    print(f"[fetch] 拉取 {SPY_TICKER} {start} → {today}（覆盖最近 {REFRESH_TRADING_DAYS} 个交易日）", file=sys.stderr)
    if _USE_CURL:
        print("[fetch] 使用 curl_cffi 浏览器指纹模式", file=sys.stderr)

    raw = _download_with_retry(
        SPY_TICKER,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
    )

    if raw.empty:
        if existing is not None:
            print("[fetch] yfinance 未返回新数据，使用本地缓存。", file=sys.stderr)
            return existing.tail(days)
        print("⚠️  yfinance 未返回 SPY 数据，请检查网络或 ticker。", file=sys.stderr)
        sys.exit(1)

    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    raw = raw.reset_index()
    raw.columns = [c.lower() for c in raw.columns]
    raw = raw.rename(columns={"price": "close"}) if "price" in raw.columns else raw
    for candidate in ("date", "datetime", "index"):
        if candidate in raw.columns:
            raw = raw.rename(columns={candidate: "date"})
            break
    raw["date"] = pd.to_datetime(raw["date"]).dt.normalize()

    cols = ["date", "open", "high", "low", "close", "volume"]
    for c in cols:
        if c not in raw.columns:
            raw[c] = None
    new_data = raw[cols].dropna(subset=["close"])

    if existing is not None:
        combined = pd.concat([existing, new_data], ignore_index=True)
        combined = combined.drop_duplicates(subset=["date"], keep="last").sort_values("date")
    else:
        combined = new_data.sort_values("date")

    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(CSV_PATH, index=False)
    print(f"[fetch] 已写入 {CSV_PATH}（共 {len(combined)} 行）", file=sys.stderr)

    return combined.tail(days)


def print_output(df: pd.DataFrame) -> None:
    r = ESM_SPY_RATIO
    start_str = df["date"].iloc[0].strftime("%Y-%m-%d")
    end_str = df["date"].iloc[-1].strftime("%Y-%m-%d")

    print("# SPY 实时行情 + ESM 换算（MMA 校验数据）\n")
    print("- 数据源：yfinance `SPY`（与 ES=F 同源链路）")
    print(f"- 换算合约：{RATIO_CONTRACT}")
    print(f"- 当前 ratio：`ESM ≈ SPY × {r}`（最后校准 {RATIO_LAST_UPDATED}）")
    print(f"- 本地缓存：{CSV_PATH}（增量更新）")
    print(f"- 拉取窗口：{start_str} → {end_str}（{len(df)} 个交易日）")
    print("- 校准提醒：每月 1 日重算 ratio（取当月 MMA 周报报价 ESM ÷ 同日 SPY 高点）\n")

    print(
        "| 日期 | SPY Open | SPY High | SPY Low | SPY Close | "
        "ESM Open | ESM High | ESM Low | ESM Close |"
    )
    print(
        "|------|---------:|---------:|--------:|----------:|"
        "---------:|---------:|--------:|----------:|"
    )
    for _, row in df.iterrows():
        d = row["date"].strftime("%Y-%m-%d")
        so, sh, sl, sc = row["open"], row["high"], row["low"], row["close"]
        print(
            f"| {d} | {so:.2f} | {sh:.2f} | {sl:.2f} | {sc:.2f} | "
            f"{so * r:.1f} | {sh * r:.1f} | {sl * r:.1f} | {sc * r:.1f} |"
        )

    last, prev = df.iloc[-1], df.iloc[-2] if len(df) >= 2 else df.iloc[-1]
    chg = (last["close"] - prev["close"]) / prev["close"] * 100
    print(f"\n## 最新交易日摘要（{df['date'].iloc[-1].strftime('%Y-%m-%d')}）")
    print(f"- SPY 收盘：{last['close']:.2f}（日变化 {chg:+.2f}%）")
    print(f"- ESM 等价收盘：{last['close'] * r:.1f}")
    print(f"- SPY 日内振幅：{last['low']:.2f} ~ {last['high']:.2f}")
    print(f"- ESM 等价振幅：{last['low'] * r:.1f} ~ {last['high'] * r:.1f}")


def main():
    parser = argparse.ArgumentParser(
        description="拉取 SPY 行情（yfinance）并换算 ESM 等价位，增量维护 data/spy_daily.csv（MMA 校验用）"
    )
    parser.add_argument("--days", type=int, default=10, help="输出最近 N 个交易日，默认 10")
    args = parser.parse_args()

    df = fetch_spy(args.days)
    print_output(df)


if __name__ == "__main__":
    main()
