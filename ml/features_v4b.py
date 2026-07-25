# -*- coding: utf-8 -*-
"""
特征 V4b = V3 全部特征 + 单一布尔 czsc_buy_today（当日恰好触发任意类买点=1）。

用于验证用户提议：把 czsc 简化为「出现买点即 1，否则 0」的单布尔特征，
与 baseline(v3_n2) 做完整 Walk-Forward 对比。唯一变量 = 这一列布尔。
"""
import pandas as pd

from ml import features_v3
from src.indicators.czsc_bsp import compute_czsc_bsp

_COL = "czsc_buy_today"


def build_features(labeled_df: pd.DataFrame, spy_df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    result, feature_cols = features_v3.build_features(labeled_df, spy_df)
    czsc_df, _ = compute_czsc_bsp(spy_df)
    print(f"  [Features V4b] 并入单布尔特征 {_COL}")
    result = result.merge(czsc_df[["date", _COL]], on="date", how="left")
    result[_COL] = result[_COL].fillna(0.0)
    return result, feature_cols + [_COL]
