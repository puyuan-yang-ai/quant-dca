"""
经济回测:把 Walk-Forward 拼接的样本外概率包装成 Entry 过滤器,接 backtest_engine
跑 A(NDay5 全信号) vs B(NDay5 + 模型过滤),用标准化执行层。
读数:扣成本 Sharpe / 回撤 / 总收益、条件收益差、Expectancy、收益差 t 检验、阈值扫描曲线。
不改任何现有文件。
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats

from src.data_loader import load_data
from src.backtest_engine import BacktestEngine
from src.strategies.composable import ComposableStrategy
from src.modules.tiers import FixedTiers
from src.modules.position import FixedPyramid
from src.modules.take_profit import NoTakeProfit
from src.modules.entry import NDayConfirmEntry, OOSProbaEntry
from experiments.configs import DATA_FILE, SMH_FILE, FEE_RATE
from ml.versions import ACTIVE_VERSION, VERSIONS

ROOT = Path(__file__).parent.parent
OUTPUT_DIR = ROOT / "output"

# 标准化执行层(照搬 scripts/compare_signals.py)
STD_TIERS = FixedTiers(drops=(0.02, 0.05, 0.10))
STD_POSITION = FixedPyramid(market_shares=1, limit_shares=(0, 0, 0))
STD_TP = NoTakeProfit()


def _engine_date_format_sample():
    """返回引擎 DATA_FILE 的首个 day['date'] 字符串,用于核对格式。"""
    data = load_data(str(ROOT / DATA_FILE))
    return data[0]["date"] if data else None


def _to_engine_date_strings(dates):
    """把 OOS 概率表的日期转成引擎 day['date'] 用的字符串格式。
    引擎 DATA_FILE 日期形如 'YYYY-MM-DD'(纯日期);若实测不同,在此调整。"""
    return pd.to_datetime(pd.Series(dates)).dt.strftime("%Y-%m-%d").tolist()


def _run_engine(entry, start, end):
    data = load_data(str(ROOT / DATA_FILE), start, end)
    smh = load_data(str(ROOT / SMH_FILE), start, end)
    strat = ComposableStrategy(tiers=STD_TIERS, entry=entry,
                               position=STD_POSITION, take_profit=STD_TP)
    return BacktestEngine(data, smh, FEE_RATE, strat).run()


def run_economics(version=None):
    version = version or ACTIVE_VERSION
    # A 基准的候选全集 = 该版本自身的 NDay 门槛
    n_days = VERSIONS.get(version, {}).get("signal", {}).get("n_days", 5)
    oos_csv = OUTPUT_DIR / f"oos_proba_{version}.csv"
    if not oos_csv.exists():
        raise FileNotFoundError(f"先跑 ml.eval_walkforward 生成 {oos_csv}")
    oos = pd.read_csv(oos_csv, parse_dates=["date"])

    # OOS 回测区间
    start = oos["date"].min().strftime("%Y-%m-%d")
    end = oos["date"].max().strftime("%Y-%m-%d")

    # --- 日期对齐自检(关键)---
    eng_sample = _engine_date_format_sample()
    oos_strs = _to_engine_date_strings(oos["date"])
    eng_dates = {d["date"] for d in load_data(str(ROOT / DATA_FILE), start, end)}
    hit = len(set(oos_strs) & eng_dates)
    print(f"[对齐自检] 引擎日期样例={eng_sample!r}  OOS日期样例={oos_strs[0]!r}  "
          f"命中 {hit}/{len(oos_strs)}")
    if hit == 0:
        raise RuntimeError("OOS 日期与引擎日期零命中:格式不一致,请修正 _to_engine_date_strings")

    # --- 构造 pass_dates ---
    pass_fi = oos[oos["proba"] > oos["fold_threshold"]]["date"]
    pass_05 = oos[oos["proba"] > 0.5]["date"]
    pass_fi_strs = _to_engine_date_strings(pass_fi)
    pass_05_strs = _to_engine_date_strings(pass_05)

    # --- 三组引擎回测（A 基准用该版本自身的 NDay 门槛）---
    eng_A = _run_engine(NDayConfirmEntry(n_days=n_days), start, end)
    eng_Bfi = _run_engine(OOSProbaEntry(pass_fi_strs), start, end)
    eng_B05 = _run_engine(OOSProbaEntry(pass_05_strs), start, end)

    def pick(m):
        return {"sharpe_ratio": m["sharpe_ratio"], "max_drawdown": m["max_drawdown"],
                "total_return": m["total_return"], "calmar_ratio": m["calmar_ratio"],
                "buy_count": m.get("buy_count", 0)}

    # --- 条件收益(事件研究)---
    fr = oos["forward_return"].values
    is_pass = (oos["proba"] > oos["fold_threshold"]).values
    e_pass = float(fr[is_pass].mean()) if is_pass.sum() else float("nan")
    e_skip = float(fr[~is_pass].mean()) if (~is_pass).sum() else float("nan")
    e_all = float(fr.mean())
    # Expectancy(按打/不打的 20日远期收益)
    win = fr[is_pass]
    expectancy = float(win.mean()) if len(win) else float("nan")
    if is_pass.sum() > 5 and (~is_pass).sum() > 5:
        t_stat, t_p = stats.ttest_ind(fr[is_pass], fr[~is_pass])
    else:
        t_stat, t_p = 0.0, 1.0

    # --- 阈值扫描 ---
    sweep = []
    for thr in np.round(np.arange(0.30, 0.71, 0.05), 2):
        pd_dates = _to_engine_date_strings(oos[oos["proba"] > thr]["date"])
        if not pd_dates:
            sweep.append({"thr": float(thr), "n": 0, "sharpe": float("nan"),
                          "e_fwd": float("nan")})
            continue
        m = _run_engine(OOSProbaEntry(pd_dates), start, end)
        mask = (oos["proba"] > thr).values
        sweep.append({"thr": float(thr), "n": int(mask.sum()),
                      "sharpe": float(m["sharpe_ratio"]),
                      "e_fwd": float(oos["forward_return"].values[mask].mean())})

    # --- 出图 ---
    OUTPUT_DIR.mkdir(exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle(f"Economic Backtest A vs B (OOS {start}~{end})", fontsize=13, fontweight="bold")
    ax = axes[0]
    ax.plot(eng_A["dates"], eng_A["daily_values"], label=f"A all-NDay{n_days} (buys={eng_A.get('buy_count',0)})")
    ax.plot(eng_Bfi["dates"], eng_Bfi["daily_values"], label=f"B fold-thr (buys={eng_Bfi.get('buy_count',0)})")
    ax.plot(eng_B05["dates"], eng_B05["daily_values"], label=f"B thr=0.5 (buys={eng_B05.get('buy_count',0)})")
    ax.set_title("Equity Curve"); ax.legend(); ax.set_xticks([])
    ax = axes[1]
    sdf = pd.DataFrame(sweep)
    ax.plot(sdf["thr"], sdf["sharpe"], marker="o", color="steelblue", label="Sharpe")
    ax.set_xlabel("threshold"); ax.set_ylabel("Sharpe"); ax.set_title("Threshold Sweep")
    ax2 = ax.twinx(); ax2.bar(sdf["thr"], sdf["n"], width=0.02, alpha=0.3, color="gray")
    ax2.set_ylabel("signal count")
    plt.tight_layout()
    plot_path = OUTPUT_DIR / f"eval_economics_{version}.png"
    plt.savefig(plot_path, dpi=150, bbox_inches="tight"); plt.close()

    # --- 打印报告 ---
    print("\n" + "=" * 60)
    print(f"  经济回测 A vs B (OOS {start} ~ {end})")
    print("=" * 60)
    print(f"  {'组':<22}{'Sharpe':>9}{'MaxDD':>9}{'总收益':>9}{'买入数':>8}")
    for name, m in [(f"A 全NDay{n_days}", eng_A), ("B 折内阈值", eng_Bfi), ("B 阈值0.5", eng_B05)]:
        print(f"  {name:<22}{m['sharpe_ratio']:>9.2f}{m['max_drawdown']*100:>8.1f}%"
              f"{m['total_return']*100:>8.1f}%{m.get('buy_count',0):>8}")
    print("-" * 60)
    print(f"  条件20日收益: 打={e_pass*100:+.2f}%  不打={e_skip*100:+.2f}%  全打={e_all*100:+.2f}%")
    print(f"  收益差 t={t_stat:.2f} p={t_p:.4f} {'显著' if t_p<0.05 else '不显著'}")
    print(f"  [Output] {plot_path}")
    print("=" * 60)

    return {
        "engine_A": pick(eng_A), "engine_B_foldinternal": pick(eng_Bfi),
        "engine_B_05": pick(eng_B05),
        "conditional": {"e_pass": e_pass, "e_skip": e_skip, "e_all": e_all,
                        "expectancy": expectancy, "t_stat": float(t_stat), "t_p": float(t_p)},
        "sweep": sweep, "plot_path": str(plot_path), "period": [start, end],
    }


def main():
    p = argparse.ArgumentParser(description="经济回测 A vs B")
    p.add_argument("--version", default=None)
    args = p.parse_args()
    run_economics(version=args.version)


if __name__ == "__main__":
    main()
