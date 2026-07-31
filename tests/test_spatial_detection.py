"""空间 GT 端到端检测评估辅助函数校验。"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ml.research.eval_spatial_detection import _binary_metrics, _signal_clusters


def test_binary_metrics():
    target = np.array([1, 1, 0, 0, 1], dtype=bool)
    predicted = np.array([1, 0, 1, 0, 1], dtype=bool)

    result = _binary_metrics(target, predicted)

    assert result["tp"] == 2
    assert result["fp"] == 1
    assert result["fn"] == 1
    assert result["tn"] == 1
    assert np.isclose(result["precision"], 2 / 3)
    assert np.isclose(result["recall"], 2 / 3)
    assert np.isclose(result["f1"], 2 / 3)
    assert np.isclose(result["accuracy"], 3 / 5)


def test_signal_clusters():
    clusters = _signal_clusters([8, 2, 3, 10, 11, 12])

    assert [cluster.tolist() for cluster in clusters] == [
        [2, 3],
        [8],
        [10, 11, 12],
    ]


if __name__ == "__main__":
    test_binary_metrics()
    test_signal_clusters()
    print("[测试] 空间 GT 端到端检测辅助函数校验通过")
