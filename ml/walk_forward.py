"""Walk-Forward 评估的纯逻辑:扩展窗切分 + Purge/Embargo + 样本唯一性权重。"""
import numpy as np
import pandas as pd


def make_expanding_folds(dates, n_folds=4, min_train=20):
    """
    扩展窗(anchored)切分:训练集起点固定、逐折延长。
    把"测试区"(min_train 之后的样本)等分成 n_folds 段连续 chunk;
    第 i 折 train = 该 chunk 之前的全部样本,test = 该 chunk。

    Args:
        dates: 按时间升序的样本日期 Series(索引 0..N-1)
    Returns:
        [(train_idx ndarray, test_idx ndarray), ...]
    """
    n = len(dates)
    if min_train >= n:
        raise ValueError(f"min_train({min_train}) >= 样本数({n}),样本太少")
    test_region = np.arange(min_train, n)
    chunks = np.array_split(test_region, n_folds)
    folds = []
    for chunk in chunks:
        if len(chunk) == 0:
            continue
        test_idx = chunk
        train_idx = np.arange(0, test_idx.min())
        folds.append((train_idx, test_idx))
    return folds


def purge_embargo_mask(train_dates, test_dates, horizon_days=28):
    """
    返回训练集布尔掩码(True=保留)。
    剔除"标签窗口伸进测试期 / 落在测试期前 embargo 缓冲内"的训练样本:
    即 train_date + horizon_days >= test_start 的样本被剔除。
    horizon_days 同时承担 purge(标签重叠)与 embargo(特征自相关缓冲)。
    """
    train_dates = pd.to_datetime(pd.Series(train_dates).values)
    test_start = pd.to_datetime(pd.Series(test_dates).values).min()
    cutoff = test_start - pd.Timedelta(days=horizon_days)
    return (train_dates <= cutoff)


def uniqueness_weights(dates, horizon_days=28):
    """
    样本唯一性权重(López de Prado 简化版):
    每个样本的标签窗口 = [date, date+horizon_days]。
    权重 = 1 / (与该样本标签窗口重叠的样本数),归一化到 (0, 1]。
    重叠越多 → 越"虚胖" → 权重越低。
    """
    d = pd.to_datetime(pd.Series(dates).reset_index(drop=True))
    h = pd.Timedelta(days=horizon_days)
    n = len(d)
    overlap_count = np.ones(n)
    for i in range(n):
        start_i, end_i = d[i], d[i] + h
        overlap = ((d <= end_i) & (d + h >= start_i)).sum()
        overlap_count[i] = overlap
    w = 1.0 / overlap_count
    return w / w.max()
