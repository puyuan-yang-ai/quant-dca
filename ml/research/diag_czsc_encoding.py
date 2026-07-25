# -*- coding: utf-8 -*-
"""
诊断：czsc 买点特征「离散 vs 布尔」编码消融。

对比在 v3_n2 候选(NDay2)+sl_proximity 标签下，不同 czsc 编码对标签的区分力：
  - 离散 last_buy_type (0/1/2/3, 现行)
  - 单布尔 any-buy-recent (近 N 日内任一类买点出现=1)
  - 三布尔 buy1/2/3-recent
  - 三布尔 buy1/2/3-today (当日恰好触发)
  - 仅 三买-recent
读数：单特征区分力 max(AUC,1-AUC) + 单次 80/20 holdout 的 base+编码 OOS AUC（仅看方向）。
"""
import os
import sys
import importlib

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from xgboost import XGBClassifier

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from ml.labeling import load_spy
from ml.versions import VERSIONS
from ml.train_export import _build_dataset
from src.chan.czsc_vendor import CZSC
from src.chan.czsc_vendor.utils.tas import update_ma_cache
from src.indicators.czsc_bsp import _BSP_FUNCS, _buy_type_code, _to_raw_bars, compute_czsc_bsp

WINDOW = 3  # "近 N 日内出现" 的窗口


def per_type_flags(spy_df, window=WINDOW):
    """逐根因果回放，产出每日 czsc 买点的各类布尔编码。"""
    bars = _to_raw_bars(spy_df)
    n = len(bars)
    c_full = CZSC(bars, max_bi_num=n)
    update_ma_cache(c_full, ma_type="SMA", timeperiod=21)
    update_ma_cache(c_full, ma_type="SMA", timeperiod=34)

    c = CZSC(bars[:1], max_bi_num=n)
    NEG = -10 ** 9
    fire_idx = {1: NEG, 2: NEG, 3: NEG}
    last_state = None
    cols = {k: np.zeros(n) for k in
            ["b1_today", "b2_today", "b3_today", "b1_rec", "b2_rec", "b3_rec", "any_rec"]}

    for i in range(1, n):
        c.update(bars[i])
        L = len(c.bi_list)
        ft = {1: 0, 2: 0, 3: 0}
        if L >= 7:
            anchor = c.bi_list[-1]
            st = (L, anchor.fx_b.dt)
            if st != last_state:
                last_state = st
                for fn in _BSP_FUNCS:
                    try:
                        sig = fn(c, di=1)
                    except Exception:
                        continue
                    for v in sig.values():
                        code = _buy_type_code(v.split("_")[0])
                        if code:
                            ft[code] = 1
                            fire_idx[code] = i
        cols["b1_today"][i] = ft[1]
        cols["b2_today"][i] = ft[2]
        cols["b3_today"][i] = ft[3]
        cols["b1_rec"][i] = 1.0 if (i - fire_idx[1] <= window) else 0.0
        cols["b2_rec"][i] = 1.0 if (i - fire_idx[2] <= window) else 0.0
        cols["b3_rec"][i] = 1.0 if (i - fire_idx[3] <= window) else 0.0
        cols["any_rec"][i] = max(cols["b1_rec"][i], cols["b2_rec"][i], cols["b3_rec"][i])

    out = pd.DataFrame({"date": spy_df["date"].values})
    for k, arr in cols.items():
        out[f"czsc_{k}"] = arr
    return out


def single_auc(y, x):
    x = np.asarray(x, float)
    if len(np.unique(y)) < 2 or np.nanstd(x) == 0:
        return float("nan")
    a = roc_auc_score(y, x)
    return max(a, 1 - a)


def main():
    cfg = VERSIONS["v3_n2"]
    fm = importlib.import_module(cfg["features_module"])
    lab = cfg["labeling"]
    kw = {k: v for k, v in lab.items() if k != "method"}
    data, base_cols = _build_dataset(lab["method"], fm, n_days=cfg["signal"]["n_days"], **kw)
    data = data.sort_values("date").reset_index(drop=True)

    spy = load_spy()
    flags = per_type_flags(spy)
    disc, _ = compute_czsc_bsp(spy)  # 含离散 czsc_last_buy_type
    disc = disc[["date", "czsc_last_buy_type"]]

    data = data.merge(flags, on="date", how="left").merge(disc, on="date", how="left")
    y = data["label"].values

    enc_groups = {
        "离散 last_buy_type (现行)": ["czsc_last_buy_type"],
        "单布尔 any_rec(近3日任一买点)": ["czsc_any_rec"],
        "三布尔 b1/2/3_rec(近3日)": ["czsc_b1_rec", "czsc_b2_rec", "czsc_b3_rec"],
        "三布尔 b1/2/3_today(当日)": ["czsc_b1_today", "czsc_b2_today", "czsc_b3_today"],
        "仅 三买_rec(近3日)": ["czsc_b3_rec"],
    }

    print("\n=== 单特征区分力 max(AUC,1-AUC) ===")
    for name in ["czsc_any_rec", "czsc_b1_rec", "czsc_b2_rec", "czsc_b3_rec",
                 "czsc_b1_today", "czsc_b2_today", "czsc_b3_today", "czsc_last_buy_type"]:
        col = data[name].values
        rate1 = y[col > 0].mean() if (col > 0).sum() else float("nan")
        print(f"  {name:<22} AUC={single_auc(y, col):.3f}  触发数={int((col>0).sum()):<5} 触发时正例率={rate1:.3f} (基线{y.mean():.3f})")

    split = int(len(data) * 0.8)

    def holdout_auc(feat):
        m = XGBClassifier(n_estimators=100, max_depth=4, learning_rate=0.1,
                          eval_metric="logloss", random_state=42, verbosity=0)
        m.fit(data[feat].values[:split], y[:split])
        p = m.predict_proba(data[feat].values[split:])[:, 1]
        return roc_auc_score(y[split:], p)

    print("\n=== base + 编码 的 holdout OOS AUC（仅看方向）===")
    print(f"  {'base 21 列 (无 czsc)':<32} {holdout_auc(base_cols):.4f}")
    for name, feats in enc_groups.items():
        print(f"  {('base + ' + name):<32} {holdout_auc(base_cols + feats):.4f}")


if __name__ == "__main__":
    main()
