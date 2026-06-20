import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd
from ml.walk_forward import make_expanding_folds, purge_embargo_mask, uniqueness_weights

def test_make_expanding_folds_basic():
    dates = pd.Series(pd.date_range("2015-01-01", periods=100, freq="D"))
    folds = make_expanding_folds(dates, n_folds=4, min_train=20)
    assert len(folds) == 4
    # 扩展窗:训练集只增不减
    prev_train_end = -1
    for train_idx, test_idx in folds:
        assert len(train_idx) > 0 and len(test_idx) > 0
        assert train_idx.max() < test_idx.min()      # 训练全在测试之前
        assert len(train_idx) >= prev_train_end       # 训练集单调增长
        prev_train_end = len(train_idx)

def test_purge_embargo_removes_boundary():
    # 训练日期 day0..day40,测试从 day50 开始;horizon=28 天
    train_dates = pd.to_datetime([f"2015-01-{d:02d}" for d in range(1, 28)])  # 1..27
    test_dates = pd.to_datetime(["2015-02-01"])                               # 2/1
    mask = purge_embargo_mask(train_dates, test_dates, horizon_days=28)
    # 距 2/1 不足 28 天的训练样本应被剔除(mask=False)
    assert mask.sum() < len(train_dates)
    # 1/1 距 2/1 = 31 天 > 28,应保留
    assert mask[0] == True
    # 1/27 距 2/1 = 5 天 < 28,应剔除
    assert mask[-1] == False

def test_uniqueness_weights_range():
    dates = pd.to_datetime(["2015-01-01", "2015-01-02", "2015-06-01"])
    w = uniqueness_weights(dates, horizon_days=28)
    assert len(w) == 3
    assert np.all(w > 0) and np.all(w <= 1.0)
    # 1/1 与 1/2 标签窗口高度重叠 → 权重应低于孤立的 6/1
    assert w[0] < w[2] and w[1] < w[2]

if __name__ == "__main__":
    test_make_expanding_folds_basic()
    test_purge_embargo_removes_boundary()
    test_uniqueness_weights_range()
    print("OK")
