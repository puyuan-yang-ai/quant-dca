# -*- coding: utf-8 -*-
"""
特征 V4 = V3 全部特征 + czsc 缠论买卖点特征（只加不减）。

唯一变量相对 v3_n2：在原有 21 个特征基础上，附加 5 列 czsc 因果特征
（见 src/indicators/czsc_bsp.py）。标签、候选（NDay）、模型超参均不变，
用于干净 A/B：v3_n2 ↔ v4 仅差「是否含 czsc 5 列」。
"""
import pandas as pd

from ml import features_v3
from src.indicators.czsc_bsp import compute_czsc_bsp


def build_features(labeled_df: pd.DataFrame, spy_df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """复用 V3 特征，再并入 czsc 每日因果特征。

    Returns:
        (data_df, feature_cols)
    """
    result, feature_cols = features_v3.build_features(labeled_df, spy_df)

    czsc_df, czsc_cols = compute_czsc_bsp(spy_df)
    print(f"  [Features V4] 并入 czsc 特征 {len(czsc_cols)} 列")
    result = result.merge(czsc_df, on="date", how="left")

    return result, feature_cols + czsc_cols
