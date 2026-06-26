"""
轻量只读诊断：NDay 门槛 n 的信号数、正样本率、信号质量分布 + 池内可分性。

无需训练模型，秒级出结果。用于快速感知：
  - 各 N 的信号数量级（排除"样本太少"假设）
  - 高门槛是否真的筛出更高质量信号
  - 候选池内部"好坏可分度"（ML 理论上界）

用法：
  python -m ml.research.diag_threshold_quality
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from ml.labeling import load_spy, generate_nday_signals

FWD_DAYS = 20


def run(ns=(1, 2, 3, 4, 5, 6, 7), cutoff_date="2026-06-25"):
    df = load_spy()
    df = df[df["date"] <= cutoff_date].reset_index(drop=True)
    close = df["close"].values
    n_total = len(df)
    fwd = pd.Series(close).shift(-FWD_DAYS) / pd.Series(close) - 1
    base = fwd.mean()

    print(f"SPY 总交易日: {n_total}  ({df['date'].iloc[0].date()} ~ {df['date'].iloc[-1].date()})")
    print(f"基准: 全样本 {FWD_DAYS}日远期收益均值 = {base*100:+.2f}%  正率 = {(fwd>0).mean()*100:.1f}%\n")

    print(f"{'门槛':>5} {'信号数':>7} {'占比':>6} {'远期收益':>9} {'正率':>6} {'胜出基准':>9} {'std':>6}")
    print("-" * 60)
    for n in ns:
        sig = generate_nday_signals(df, n=n)
        idx = np.where(sig.values)[0]
        valid = idx[idx < n_total - FWD_DAYS]
        rets = fwd.values[valid]
        rets = rets[~np.isnan(rets)]
        if len(rets) == 0:
            print(f"{n:>5} {0:>7}")
            continue
        print(f"{n:>5} {int(sig.sum()):>7} {sig.sum()/n_total*100:>5.1f}% "
              f"{rets.mean()*100:>+8.2f}% {(rets>0).mean()*100:>5.1f}% "
              f"{(rets.mean()-base)*100:>+8.2f}% {rets.std()*100:>5.2f}%")

    print("\n候选池内部可分性（用未来收益做'完美ML'上界）：")
    for n in ns:
        sig = generate_nday_signals(df, n=n)
        idx = np.where(sig.values)[0]
        valid = idx[idx < n_total - FWD_DAYS]
        rets = fwd.values[valid]
        rets = rets[~np.isnan(rets)]
        if len(rets) < 10:
            continue
        med = np.median(rets)
        top, bot = rets[rets >= med].mean(), rets[rets < med].mean()
        print(f"  NDay{n} (n={len(rets)}): 上半 {top*100:+.2f}% vs 下半 {bot*100:+.2f}% "
              f"→ 价差 {(top-bot)*100:.2f}pp")


if __name__ == "__main__":
    run()
