"""
阈值扫描 —— 事件级 Precision/Recall（对齐"尽可能多且准地抓局部低点"）。

第一性原理：
  - 目的 = 抓"局部低点"。局部低点是稀疏、孤立的事件。
  - 因此计量单位是【独立的真底事件】，不是【信号日】。一个底抓到就算数，抓几次不额外加分。
  - 纯阈值过滤（概率 > 阈值即信号），连续加仓由人工把关，脚本不做冷却。

口径（与训练标签 GT 完全一致）：
  - 真底 = detect_swing_lows(sl_n)  —— 默认 sl_n=7
  - 信号"抓到"某真底 = 信号日落在该真底 ± k 天内 —— 默认 k=3

指标：
  - 事件级 Recall  = 被至少一个信号覆盖的真底数 / 全部真底数        （"多"）
  - 事件级 Precision = 命中真底的信号数 / 总信号数                  （"准"）
  - 信号簇数 = 把连续信号日并成簇后的个数（衡量"加仓批次"量级，供人工把关参考）

用法：
  python -m ml.research.sweep_threshold_event                 # 默认 N=2, sl_n=7, k=3
  python -m ml.research.sweep_threshold_event --n 2 --sl-n 7 --k 3
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import ml.train_export as te
from ml.labeling import run as run_labeling, load_spy
from src.indicators import detect_swing_lows

_CURRENT_N = {"n": 2}
_orig = run_labeling


def _build_dataset_param(method, features_module, **kw):
    labeled = _orig(n_days=_CURRENT_N["n"], method=method, **kw)
    spy_df = load_spy()
    data, cols = features_module.build_features(labeled, spy_df)
    return data.dropna(subset=cols).reset_index(drop=True), cols


te._build_dataset = _build_dataset_param
import ml.eval_walkforward as ewf  # noqa: E402
ewf._build_dataset = _build_dataset_param
from ml.eval_walkforward import run_walkforward  # noqa: E402


def _count_clusters(sorted_idx):
    """把信号的整数位置序列按"连续"并簇，返回簇数。"""
    if len(sorted_idx) == 0:
        return 0
    arr = np.sort(sorted_idx)
    return 1 + int((np.diff(arr) > 1).sum())


def run(n=2, sl_n=7, k=3, folds=4):
    _CURRENT_N["n"] = n
    wf = run_walkforward(version_tag=f"thr_n{n}", n_folds=folds)
    oos = wf["oos"].reset_index(drop=True)
    oos_dates = pd.to_datetime(oos["date"])

    # 全量 SPY 上找 swing low（真底事件），口径与 GT 一致
    spy = load_spy()
    sl = detect_swing_lows(spy["close"].tolist(),
                           spy["date"].dt.strftime("%Y-%m-%d").tolist(), sl_n)
    sl_dates = pd.to_datetime([s["date"] for s in sl])

    # 只统计落在 OOS 区间内的真底（公平：模型只在 OOS 段出过概率）
    lo, hi = oos_dates.min(), oos_dates.max()
    sl_in = sl_dates[(sl_dates >= lo) & (sl_dates <= hi)]
    total_bottoms = len(sl_in)

    proba = oos["proba"].values
    k_td = pd.Timedelta(days=k)

    print("\n" + "=" * 92)
    print(f"  阈值扫描（事件级）N={n}  真底=swing_low(sl_n={sl_n})  附近=±{k}天  "
          f"OOS真底总数={total_bottoms}")
    print("=" * 92)
    print(f"{'阈值':>5} {'信号数':>6} {'信号簇':>6} | "
          f"{'命中真底信号':>11} {'事件Precision':>13} | "
          f"{'抓到真底数':>9} {'事件Recall':>11} | {'综合F1':>7}")
    print("-" * 92)

    rows = []
    for thr in np.round(np.arange(0.10, 0.71, 0.05), 2):
        mask = proba > thr
        sig_dates = oos_dates[mask]
        sig_pos = np.where(mask)[0]
        n_sig = int(mask.sum())
        n_cluster = _count_clusters(sig_pos)
        if n_sig == 0:
            rows.append((thr, 0, 0, 0.0, 0, 0.0, 0.0)); continue

        sl_arr = sl_in.values.astype("datetime64[D]")
        sig_arr = sig_dates.values.astype("datetime64[D]")

        # 事件 precision: 每个信号是否落在任一真底 ±k 内
        hit_sig = 0
        for d in sig_arr:
            if len(sl_arr) and (np.abs((sl_arr - d).astype(int)) <= k).any():
                hit_sig += 1
        ev_prec = hit_sig / n_sig

        # 事件 recall: 每个真底是否被任一信号覆盖
        caught = 0
        for b in sl_arr:
            if (np.abs((sig_arr - b).astype(int)) <= k).any():
                caught += 1
        ev_rec = caught / total_bottoms if total_bottoms else float("nan")

        f1 = (2 * ev_prec * ev_rec / (ev_prec + ev_rec)) if (ev_prec + ev_rec) > 0 else 0.0
        rows.append((thr, n_sig, n_cluster, ev_prec, caught, ev_rec, f1))
        print(f"{thr:>5.2f} {n_sig:>6} {n_cluster:>6} | "
              f"{hit_sig:>11} {ev_prec*100:>12.1f}% | "
              f"{caught:>9} {ev_rec*100:>10.1f}% | {f1:>7.3f}")

    print("=" * 92)
    print("解读（第一性原理：抓尽可能多且准的【独立局部低点】）：")
    print("- 事件Recall = 被信号覆盖的真底数 / OOS真底总数 → '多抓底'")
    print("- 事件Precision = 落在真底±k的信号数 / 总信号数 → '准'")
    print("- 信号簇 = 连续信号并簇后的批次数,衡量'加仓批次'量级(人工把关参考)")
    print("- 阈值越低: Recall↑(多抓) 但 Precision↓(假信号多)、信号簇↑(加仓频繁)")
    print("- 找'事件F1'高且信号簇可接受的阈值,即兼顾多与准的实盘落点")

    df = pd.DataFrame(rows, columns=["threshold", "n_signal", "n_cluster",
                                     "ev_precision", "caught", "ev_recall", "ev_f1"])
    out = ROOT / "output" / f"sweep_threshold_event_n{n}.csv"
    df.to_csv(out, index=False)
    print(f"[Output] {out}")
    return df


def main():
    p = argparse.ArgumentParser(description="事件级阈值扫描")
    p.add_argument("--n", type=int, default=2, help="NDay 门槛(主旋钮固定值)")
    p.add_argument("--sl-n", type=int, default=7, help="swing low 窗口(与GT一致)")
    p.add_argument("--k", type=int, default=3, help="真底附近天数(与GT一致)")
    p.add_argument("--folds", type=int, default=4)
    args = p.parse_args()
    run(n=args.n, sl_n=args.sl_n, k=args.k, folds=args.folds)


if __name__ == "__main__":
    main()
