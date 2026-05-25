"""拉取 ES=F 期货真实行情 + VIX，增量维护 data/es_daily.csv，供 MMA 校验使用。"""
import argparse
import os
import sys
import time
import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

# ── SOCKS5 代理配置 ──────────────────────────────────────────────────────────
# 走新加坡 ECS 出口，绕过雅虎对本机 IP 的限流。
# 优先级：已有环境变量 > .env 文件 > 无代理（直连）
def _load_proxy() -> str | None:
    """从 .env 文件或环境变量读取代理地址，不在代码里硬编码密码。"""
    # 1. 已有环境变量直接用
    existing = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if existing:
        return existing
    # 2. 从项目根目录的 .env 文件读取 YAHOO_PROXY
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("YAHOO_PROXY="):
                return line.split("=", 1)[1].strip()
    return None

_PROXY = _load_proxy()

if _PROXY:
    # 注入到进程环境，让 requests / curl_cffi / yfinance 底层都能感知
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

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "es_daily.csv"
ES_TICKER = "ES=F"
VIX_TICKER = "^VIX"

# 每次运行都强制重新拉取最近这么多个交易日的数据，覆盖掉本地可能不完整的记录
# （例如假期/盘中抓到的低 Volume 数据）
REFRESH_TRADING_DAYS = 3

# 限流时最多重试次数，每次等待随机间隔
_MAX_RETRIES = 3
_RETRY_BASE_WAIT = 8  # 秒


def _download_with_retry(ticker: str, start: str, end: str) -> pd.DataFrame:
    """带重试的 yf.download，优先使用 curl_cffi session 模拟浏览器指纹。"""
    kwargs = dict(
        start=start,
        end=end,
        auto_adjust=True,
        progress=False,
    )
    if _USE_CURL and _SESSION is not None:
        kwargs["session"] = _SESSION

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            raw = yf.download(ticker, **kwargs)
            if not raw.empty:
                return raw
            # 返回空但没抛异常，视为限流或无数据
            print(f"[fetch] 第 {attempt} 次尝试返回空数据", file=sys.stderr)
        except Exception as e:
            print(f"[fetch] 第 {attempt} 次尝试失败：{e}", file=sys.stderr)

        if attempt < _MAX_RETRIES:
            wait = _RETRY_BASE_WAIT * attempt + random.uniform(1, 4)
            print(f"[fetch] 等待 {wait:.1f}s 后重试…", file=sys.stderr)
            time.sleep(wait)

    return pd.DataFrame()  # 全部重试失败，返回空 DataFrame


def _trading_days_start(n: int) -> date:
    """往前推 n 个交易日的起始日期（按自然日 * 2 保守估算，涵盖周末/假日）。"""
    return date.today() - timedelta(days=n * 2 + 3)


def fetch_es(days: int) -> pd.DataFrame:
    """拉取 ES=F 日线数据。
    策略：每次都强制重新拉取最近 REFRESH_TRADING_DAYS 个交易日的数据并覆盖本地缓存，
    避免缓存中存有盘中或假期低流动性的不完整记录；更早的历史数据保持不变。
    """
    today = date.today()

    # 加载已有缓存（可能为空）
    if CSV_PATH.exists():
        existing = pd.read_csv(CSV_PATH, parse_dates=["date"])
        existing["date"] = existing["date"].dt.normalize()
    else:
        existing = None

    # 拉取起点：用足够宽的自然日窗口确保覆盖 REFRESH_TRADING_DAYS 个交易日
    refresh_start = _trading_days_start(REFRESH_TRADING_DAYS)

    # 若缓存比 refresh_start 还早，则从缓存最早缺失处开始全量补历史
    if existing is not None:
        last_date = existing["date"].max().date()
        # 如果缓存里根本没有历史数据，从更早开始
        start = min(refresh_start, last_date + timedelta(days=1) if last_date < refresh_start else refresh_start)
    else:
        start = today - timedelta(days=days * 2 + 10)

    end = today + timedelta(days=1)  # yfinance end 是开区间

    print(f"[fetch] 拉取 {ES_TICKER} {start} → {today}（覆盖最近 {REFRESH_TRADING_DAYS} 个交易日）", file=sys.stderr)
    if _USE_CURL:
        print("[fetch] 使用 curl_cffi 浏览器指纹模式", file=sys.stderr)

    raw = _download_with_retry(
        ES_TICKER,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
    )

    if raw.empty:
        if existing is not None:
            print("[fetch] yfinance 未返回新数据，使用本地缓存。", file=sys.stderr)
            return existing.tail(days)
        print("⚠️  yfinance 未返回 ES=F 数据，请检查网络或 ticker。", file=sys.stderr)
        sys.exit(1)

    # 展平多级列名（yfinance ≥0.2 在 multi-ticker 时会出现，单 ticker 也偶发）
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    raw = raw.reset_index()
    raw.columns = [c.lower() for c in raw.columns]
    raw = raw.rename(columns={"price": "close"}) if "price" in raw.columns else raw
    # yfinance 不同版本 reset_index 后索引列名可能是 date / datetime / index
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
        # 用新拉取的数据覆盖缓存中相同日期的行（drop_duplicates 保留 last，即新数据优先）
        combined = pd.concat([existing, new_data], ignore_index=True)
        combined = combined.drop_duplicates(subset=["date"], keep="last").sort_values("date")
    else:
        combined = new_data.sort_values("date")

    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(CSV_PATH, index=False)
    print(f"[fetch] 已写入 {CSV_PATH}（共 {len(combined)} 行）", file=sys.stderr)

    return combined.tail(days)


def fetch_vix_latest() -> float | None:
    """拉取 VIX 最新收盘价，失败时返回 None。"""
    try:
        kwargs = dict(period="5d", auto_adjust=True, progress=False)
        if _USE_CURL and _SESSION is not None:
            kwargs["session"] = _SESSION
        vix = yf.download(VIX_TICKER, **kwargs)
        if isinstance(vix.columns, pd.MultiIndex):
            vix.columns = vix.columns.get_level_values(0)
        if vix.empty:
            return None
        return float(vix["Close"].iloc[-1])
    except Exception:
        return None


def iv_label(vix: float | None) -> str:
    if vix is None:
        return "无法获取"
    if vix >= 22:
        return f"{vix:.2f}（高 IV，≥22 → 优先 Credit Spread）"
    return f"{vix:.2f}（中低 IV，<22 → 优先 Debit Spread）"


def print_output(df: pd.DataFrame, vix: float | None) -> None:
    """按方案 §2.4 格式打印标准输出。"""
    start_str = df["date"].iloc[0].strftime("%Y-%m-%d")
    end_str = df["date"].iloc[-1].strftime("%Y-%m-%d")
    n = len(df)

    print("# ES 期货行情（MMA 校验数据）\n")
    print("- 数据源：yfinance ES=F（S&P 500 E-mini 连续合约）")
    print("- 已验证：ES=F 与 ESM26 一致，无需系数换算")
    print(f"- 本地缓存：{CSV_PATH}（增量更新）")
    print(f"- 拉取窗口：{start_str} → {end_str}（{n} 个交易日）\n")

    # 表头
    print("| 日期 | ES Open | ES High | ES Low | ES Close | Volume |")
    print("|------|--------:|--------:|-------:|---------:|-------:|")
    for _, row in df.iterrows():
        d = row["date"].strftime("%Y-%m-%d")
        vol = int(row["volume"]) if pd.notna(row["volume"]) else 0
        print(
            f"| {d} | {row['open']:.1f} | {row['high']:.1f} | "
            f"{row['low']:.1f} | {row['close']:.1f} | {vol:,} |"
        )

    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else last
    chg = (last["close"] - prev["close"]) / prev["close"] * 100

    print(f"\n## 最新交易日摘要（{last['date'].strftime('%Y-%m-%d')}）")
    print(f"- ES 收盘：{last['close']:.1f}（日变化 {chg:+.2f}%）")
    print(f"- ES 日内振幅：{last['low']:.1f} ~ {last['high']:.1f}")
    print(f"- **VIX 收盘：{iv_label(vix)}**")


def main():
    parser = argparse.ArgumentParser(
        description="拉取 ES=F 期货行情 + VIX，增量维护 data/es_daily.csv（MMA 校验用）"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="输出最近 N 个交易日，默认 7；首次建议用 60",
    )
    args = parser.parse_args()

    df = fetch_es(args.days)
    vix = fetch_vix_latest()
    print_output(df, vix)


if __name__ == "__main__":
    main()
