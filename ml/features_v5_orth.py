# -*- coding: utf-8 -*-
"""
特征 V5-orth（路径A 消融 A3）= v5_pa universe 上的【正交精简 base】+ czsc 5 列。

正交精简 base 由 v5_pa 数据集上的 相关聚类(|Spearman|>0.8 去冗余) + 单特征区分力(<0.52 去噪声)
筛选得到（共 10 列），用于排除"纯特征变多"对 A2 的干扰。
"""
import pandas as pd

from ml import features_v4  # = features_v3(21) + czsc 5 列

# 在 v5_pa(近底 n30p05) universe 上重选的正交精简 base（10 列）
_ORTH_BASE = [
    "ema20_dist", "breadth_min_3d", "rsi_minus_ma", "vix_regime",
    "vix_above_200ma", "confluence_5d", "sig_breadth_recent_3d",
    "sig_rsi_recent_3d", "sig_breadth", "sig_vix",
]


def build_features(labeled_df: pd.DataFrame, spy_df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    result, all_cols = features_v4.build_features(labeled_df, spy_df)
    czsc_cols = [c for c in all_cols if c.startswith("czsc_")]
    feature_cols = _ORTH_BASE + czsc_cols
    print(f"  [Features V5-orth] 正交精简 base {len(_ORTH_BASE)} + czsc {len(czsc_cols)} = {len(feature_cols)} 列")
    return result, feature_cols
