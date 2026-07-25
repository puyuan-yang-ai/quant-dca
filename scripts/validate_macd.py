# -*- coding: utf-8 -*-
"""
验证 src/indicators/macd.py 的口径正确性。

两道验证：

1) 独立交叉校验（无需外部数据，默认执行）：
   用 pandas ewm(adjust=False) 复算 EMA/DIF/DEA/hist，与 calc_macd 逐根比对。
   pandas ewm(adjust=False) 即 alpha=2/(n+1)、首值初始化的递归 EMA，
   与 TradingView ta.ema 的口径一致。此步用于保证实现无 bug（off-by-one、alpha 错、×2 等）。

2) TradingView 真值兜底校验（可选，--tv-csv 提供时执行）：
   读入从 TradingView 导出/手抄的样本 CSV，与 calc_macd 输出逐根比对。
   CSV 至少需含收盘价列；若含 DIF/DEA/Hist 列则进行数值比对。
   列名大小写不敏感，支持别名：
     close      <- close / 收盘价 / 收盘
     dif        <- dif / macd / macd line
     dea        <- dea / signal / signal line
     hist       <- hist / histogram / 柱

说明：因 EMA 指数遗忘，初值影响仅在预热段，约 3~5 倍周期后收敛。
只要分析窗口前有充足预热历史，窗口内的值必然与 TradingView 一致。

用法：
    python scripts/validate_macd.py                 # 仅独立交叉校验
    python scripts/validate_macd.py --tv-csv x.csv  # 附加 TradingView 真值校验
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.indicators.macd import calc_macd  # noqa: E402

TOL = 1e-9  # 独立交叉校验容差（应达到机器精度级别）
TV_TOL = 1e-4  # TradingView 真值容差（导出/手抄精度有限，放宽）


def _pandas_macd(closes, fast=12, slow=26, signal=9):
    """用 pandas ewm(adjust=False) 复算 MACD，作为独立参考。"""
    s = pd.Series([float(x) for x in closes], dtype="float64")
    ema_fast = s.ewm(span=fast, adjust=False).mean()
    ema_slow = s.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    hist = dif - dea
    return dif.to_numpy(), dea.to_numpy(), hist.to_numpy()


def _max_abs_diff(a, b):
    a = np.asarray(a, dtype="float64")
    b = np.asarray(b, dtype="float64")
    return float(np.max(np.abs(a - b))) if len(a) else 0.0


def cross_check(seed: int = 42, n: int = 2000) -> bool:
    """独立交叉校验：calc_macd vs pandas ewm(adjust=False)。"""
    rng = np.random.default_rng(seed)
    # 用随机游走模拟价格序列，覆盖正常波动
    closes = 100.0 + np.cumsum(rng.normal(0, 1, size=n))
    closes = closes.tolist()

    dif, dea, hist = calc_macd(closes)
    p_dif, p_dea, p_hist = _pandas_macd(closes)

    d_dif = _max_abs_diff(dif, p_dif)
    d_dea = _max_abs_diff(dea, p_dea)
    d_hist = _max_abs_diff(hist, p_hist)

    print("[独立交叉校验] calc_macd vs pandas ewm(adjust=False)")
    print(f"  样本根数: {n}")
    print(f"  max|ΔDIF|  = {d_dif:.3e}")
    print(f"  max|ΔDEA|  = {d_dea:.3e}")
    print(f"  max|Δhist| = {d_hist:.3e}")

    ok = max(d_dif, d_dea, d_hist) < TOL
    print(f"  结论: {'通过 ✓' if ok else '不通过 ✗'}（容差 {TOL:.0e}）")
    return ok


_ALIASES = {
    "close": ["close", "收盘价", "收盘", "c"],
    "dif": ["dif", "macd", "macd line", "macdline"],
    "dea": ["dea", "signal", "signal line", "signalline"],
    "hist": ["hist", "histogram", "柱", "hist."],
}


def _resolve_columns(df: pd.DataFrame) -> dict:
    lower = {c.lower().strip(): c for c in df.columns}
    resolved = {}
    for key, names in _ALIASES.items():
        for nm in names:
            if nm in lower:
                resolved[key] = lower[nm]
                break
    return resolved


def tv_check(csv_path: Path) -> bool:
    """TradingView 真值兜底校验。"""
    df = pd.read_csv(csv_path)
    cols = _resolve_columns(df)
    print(f"\n[TradingView 真值校验] {csv_path}")
    print(f"  识别到的列: {cols}")

    if "close" not in cols:
        print("  ✗ 未找到收盘价列，无法计算 MACD。")
        return False

    closes = df[cols["close"]].astype("float64").tolist()
    dif, dea, hist = calc_macd(closes)

    ok = True
    for key, series in (("dif", dif), ("dea", dea), ("hist", hist)):
        if key in cols:
            truth = df[cols[key]].astype("float64").to_numpy()
            d = _max_abs_diff(series, truth)
            passed = d < TV_TOL
            ok = ok and passed
            print(f"  max|Δ{key.upper()}| = {d:.3e}  {'✓' if passed else '✗'}")
        else:
            print(f"  （CSV 未提供 {key.upper()} 列，跳过）")

    print(f"  结论: {'通过 ✓' if ok else '不通过 ✗'}（容差 {TV_TOL:.0e}）")
    return ok


def main():
    parser = argparse.ArgumentParser(description="验证 MACD 口径")
    parser.add_argument("--tv-csv", type=Path, default=None,
                        help="TradingView 导出/手抄的样本 CSV 路径（可选）")
    args = parser.parse_args()

    ok = cross_check()
    if args.tv_csv:
        ok = tv_check(args.tv_csv) and ok

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
