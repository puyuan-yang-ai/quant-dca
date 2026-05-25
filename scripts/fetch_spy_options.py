"""
拉取 SPY 期权链，按指定腿输出实时 bid/ask/iv/delta，并计算组合净权利金和止盈触发价。
供 mma-5-order-pro Phase 2 权利金验证使用。不存 CSV，只做实时快照输出。

用法示例：
  # 单腿（调试）
  python scripts/fetch_spy_options.py --legs "call,2026-06-12,745"

  # Bull Call Spread：买 745C + 卖 760C
  python scripts/fetch_spy_options.py --legs "call,2026-06-12,745" "call,2026-06-12,760"

腿格式：type,expiry,strike
  type  : call | put
  expiry: YYYY-MM-DD（必须是 SPY 实际存在的到期日）
  strike: 整数或浮点数（如 745 或 745.0）
"""
import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

# ── SOCKS5 代理（与 fetch_es_for_mma.py 共享同一 .env 配置）────────────────
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

_proxy = _load_proxy()
if _proxy:
    os.environ.setdefault("HTTPS_PROXY", _proxy)
    os.environ.setdefault("HTTP_PROXY", _proxy)

ET = ZoneInfo("America/New_York")


def parse_leg(raw: str) -> tuple[str, str, float]:
    """解析单腿字符串，返回 (type, expiry, strike)。"""
    parts = raw.strip().split(",")
    if len(parts) != 3:
        print(f"❌ 腿格式错误：'{raw}'，正确格式为 type,expiry,strike", file=sys.stderr)
        sys.exit(1)
    leg_type = parts[0].strip().lower()
    if leg_type not in ("call", "put"):
        print(f"❌ 腿类型必须为 call 或 put，收到：'{leg_type}'", file=sys.stderr)
        sys.exit(1)
    expiry = parts[1].strip()
    try:
        strike = float(parts[2].strip())
    except ValueError:
        print(f"❌ Strike 必须为数字，收到：'{parts[2]}'", file=sys.stderr)
        sys.exit(1)
    return leg_type, expiry, strike


def get_option_chain(expiry: str) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """拉取 SPY 指定到期日的期权链，返回 (calls, puts, available_expiries)。"""
    spy = yf.Ticker("SPY")
    try:
        available = list(spy.options)  # 字符串列表，格式 YYYY-MM-DD
    except Exception as e:
        if "rate" in str(e).lower() or "429" in str(e) or "too many" in str(e).lower():
            print("❌ Yahoo Finance 限速（Rate Limited），请等待 1-2 小时后重试。", file=sys.stderr)
        else:
            print(f"❌ 拉取 SPY 期权链失败：{e}", file=sys.stderr)
        sys.exit(1)

    if expiry not in available:
        nearby = ", ".join(available[:6])
        print(f"❌ {expiry} 不是 SPY 的有效到期日。最近可用：{nearby}", file=sys.stderr)
        sys.exit(1)

    chain = spy.option_chain(expiry)
    return chain.calls, chain.puts, available


def find_strike_row(df: pd.DataFrame, strike: float, expiry: str) -> pd.Series:
    """在期权链 df 中找到指定 strike，找不到时打印最近可用并退出。"""
    if "strike" not in df.columns:
        print("❌ 期权链数据异常，缺少 strike 列。", file=sys.stderr)
        sys.exit(1)

    row = df[df["strike"] == strike]
    if row.empty:
        # 找最近的 5 个 strike
        all_strikes = sorted(df["strike"].unique())
        nearby = sorted(all_strikes, key=lambda s: abs(s - strike))[:5]
        nearby_str = ", ".join(str(int(s)) for s in nearby)
        print(
            f"❌ Strike {int(strike)} 不在 {expiry} 的期权链中。最近可用：{nearby_str}",
            file=sys.stderr,
        )
        sys.exit(1)
    return row.iloc[0]


def safe_float(val, default: float = 0.0) -> float:
    try:
        f = float(val)
        return f if pd.notna(f) else default
    except (TypeError, ValueError):
        return default


def main():
    parser = argparse.ArgumentParser(
        description="拉取 SPY 期权报价，计算组合净权利金和止盈触发价（mma-5 Phase 2 用）"
    )
    parser.add_argument(
        "--legs",
        nargs="+",
        required=True,
        metavar="type,expiry,strike",
        help="一到多个腿，格式：call,2026-06-12,745",
    )
    args = parser.parse_args()

    legs = [parse_leg(r) for r in args.legs]

    # 按到期日分批拉取期权链（同一到期日只拉一次）
    chain_cache: dict[str, tuple[pd.DataFrame, pd.DataFrame]] = {}
    for _, expiry, _ in legs:
        if expiry not in chain_cache:
            calls, puts, _ = get_option_chain(expiry)
            chain_cache[expiry] = (calls, puts)

    now_et = datetime.now(tz=ET)
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    is_market_hours = market_open <= now_et <= market_close and now_et.weekday() < 5

    print("# SPY 期权报价（实时快照）")
    print(f"- 查询时间：{now_et.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print("- 数据源：yfinance SPY option_chain")
    if not is_market_hours:
        print("- ⚠️ 当前为非交易时间，报价为上一交易日收盘快照")

    print("\n## 各腿报价\n")
    print("| 腿 | 类型 | 到期日 | Strike | Bid | Ask | Mid | IV | Delta | OI |")
    print("|----|------|--------|--------|-----|-----|-----|----|-------|----|")

    leg_rows = []
    for i, (leg_type, expiry, strike) in enumerate(legs, start=1):
        calls, puts = chain_cache[expiry]
        df = calls if leg_type == "call" else puts
        row = find_strike_row(df, strike, expiry)

        bid = safe_float(row.get("bid"))
        ask = safe_float(row.get("ask"))
        mid = round((bid + ask) / 2, 2)
        iv = safe_float(row.get("impliedVolatility"))
        delta_raw = row.get("delta") if "delta" in row.index else None
        delta_str = f"{safe_float(delta_raw):.2f}" if delta_raw is not None else "N/A"
        oi = int(safe_float(row.get("openInterest")))

        print(
            f"| L{i} | {leg_type.capitalize()} | {expiry} | {int(strike)} | "
            f"{bid:.2f} | {ask:.2f} | {mid:.2f} | {iv:.2f} | {delta_str} | {oi:,} |"
        )
        leg_rows.append({"label": f"L{i}", "type": leg_type, "expiry": expiry,
                          "strike": strike, "bid": bid, "ask": ask, "mid": mid})

    # 组合计算（仅 2 腿时输出；假设 L1 为买腿，L2 为卖腿）
    if len(leg_rows) == 2:
        l1, l2 = leg_rows[0], leg_rows[1]
        # 判断 debit 还是 credit（同类型 spread：买腿 mid > 卖腿 mid → debit）
        net = round(l1["mid"] - l2["mid"], 2)
        is_debit = net > 0
        label = "净 Debit（付出）" if is_debit else "净 Credit（收入）"
        net_abs = abs(net)

        strike_diff = abs(l1["strike"] - l2["strike"])
        max_profit = round(strike_diff - net_abs, 2) if is_debit else net_abs
        max_loss = net_abs if is_debit else round(strike_diff - net_abs, 2)
        roi = round(max_profit / max_loss * 100, 1) if max_loss > 0 else float("inf")

        tp70 = round(net_abs + 0.70 * max_profit, 2) if is_debit else round(net_abs * 0.30, 2)
        tp80 = round(net_abs + 0.80 * max_profit, 2) if is_debit else round(net_abs * 0.20, 2)

        print("\n## 组合计算（按 Mid 价）\n")
        print("| 项目 | 计算 | 结果 |")
        print("|------|------|------|")
        print(f"| {label} | L1 Mid - L2 Mid | ${net_abs:.2f} |")
        if is_debit:
            print(f"| Max Profit | Strike 差 - 净 Debit | ${max_profit:.2f} |")
            print(f"| Max Loss | 净 Debit | ${max_loss:.2f} |")
        else:
            print(f"| Max Profit | 净 Credit | ${max_profit:.2f} |")
            print(f"| Max Loss | Strike 差 - 净 Credit | ${max_loss:.2f} |")
        print(f"| ROI（Max）| Max Profit ÷ Max Loss | {roi:.1f}% |")
        print(f"| **70% 止盈触发** | | **${tp70:.2f}** |")
        print(f"| **80% 止盈触发** | | **${tp80:.2f}** |")

    print("\n## 注意事项")
    print("- ⚠️ Bid/Ask 使用收盘后快照，下单前请以实盘报价为准")
    print("- ⚠️ IV 基于 Mid Price 隐含波动率")


if __name__ == "__main__":
    main()
