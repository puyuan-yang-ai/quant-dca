"""空间 GT 因果端到端评估辅助函数校验。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ml.research.eval_spatial_e2e import (
    _calibrate_rank_threshold,
    _xirr,
)


def test_rank_threshold():
    scores = np.array([0.1, 0.2, 0.8, 0.9])
    mask = np.ones(4, dtype=bool)
    threshold, rate = _calibrate_rank_threshold(scores, mask, 0.5)
    assert np.isclose(threshold, 0.8)
    assert np.isclose(rate, 0.5)


def test_xirr():
    cashflows = [
        (pd.Timestamp("2021-01-01"), -100.0),
        (pd.Timestamp("2022-01-01"), 110.0),
    ]
    result = _xirr(cashflows)
    assert np.isclose(result, 0.1, atol=1e-4)


if __name__ == "__main__":
    test_rank_threshold()
    test_xirr()
    print("[Test] 空间 GT 因果端到端辅助函数校验通过")
