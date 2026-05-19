"""拉取 SPY 真实行情并按 ratio 换算为 ESM 等价位，供 MMA 周报校验使用。"""
import argparse
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

# ratio = MMA 周报当周高点 ESM ÷ 同日 SPY 高点。每月 1 日重新校准。
ESM_SPY_RATIO = 10.06
RATIO_LAST_UPDATED = "2026-05-18"
RATIO_CONTRACT = "ESM26 (June 2026 e-mini)"


def main():
    parser = argparse.ArgumentParser(
        description="拉取 SPY 行情并换算 ESM 等价位（MMA 校验用）"
    )
    parser.add_argument("--days", type=int, default=10, help="过去 N 个交易日，默认 10")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    load_dotenv(project_root / ".env")
    token = os.getenv("TIINGO_API_KEY")
    if not token:
        print("❌ 缺少 TIINGO_API_KEY 环境变量（检查 .env 文件）", file=sys.stderr)
        sys.exit(1)

    from tiingo import TiingoClient

    end = date.today()
    start = end - timedelta(days=args.days * 2 + 7)

    client = TiingoClient({"api_key": token, "session": True})
    df = client.get_dataframe(
        "SPY",
        frequency="daily",
        startDate=start.isoformat(),
        endDate=end.isoformat(),
    ).tail(args.days).round(2)

    r = ESM_SPY_RATIO

    print("# SPY 实时行情 + ESM 换算（MMA 校验数据）\n")
    print("- 数据源：Tiingo Daily Prices (`SPY`)")
    print(f"- 换算合约：{RATIO_CONTRACT}")
    print(f"- 当前 ratio：`ESM ≈ SPY × {r}`（最后校准 {RATIO_LAST_UPDATED}）")
    print(
        f"- 拉取窗口：{df.index[0].strftime('%Y-%m-%d')} → "
        f"{df.index[-1].strftime('%Y-%m-%d')}（{len(df)} 个交易日）"
    )
    print("- 校准提醒：每月 1 日重算 ratio（取当月 MMA 周报报价 ESM ÷ 同日 SPY 高点）\n")

    print(
        "| 日期 | SPY Open | SPY High | SPY Low | SPY Close | "
        "ESM Open | ESM High | ESM Low | ESM Close |"
    )
    print(
        "|------|---------:|---------:|--------:|----------:|"
        "---------:|---------:|--------:|----------:|"
    )
    for ts, row in df.iterrows():
        d = ts.strftime("%Y-%m-%d")
        so, sh, sl, sc = row["open"], row["high"], row["low"], row["close"]
        print(
            f"| {d} | {so:.2f} | {sh:.2f} | {sl:.2f} | {sc:.2f} | "
            f"{so * r:.1f} | {sh * r:.1f} | {sl * r:.1f} | {sc * r:.1f} |"
        )

    last, prev = df.iloc[-1], df.iloc[-2]
    chg = (last["close"] - prev["close"]) / prev["close"] * 100
    print(f"\n## 最新交易日摘要（{df.index[-1].strftime('%Y-%m-%d')}）")
    print(f"- SPY 收盘：{last['close']:.2f}（日变化 {chg:+.2f}%）")
    print(f"- ESM 等价收盘：{last['close'] * r:.1f}")
    print(f"- SPY 日内振幅：{last['low']:.2f} ~ {last['high']:.2f}")
    print(f"- ESM 等价振幅：{last['low'] * r:.1f} ~ {last['high'] * r:.1f}")


if __name__ == "__main__":
    main()
