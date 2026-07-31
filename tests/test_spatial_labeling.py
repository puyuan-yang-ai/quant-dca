"""空间 GT 标注的最小回归校验。"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ml.labeling import build_sl_price_gt, create_labels_sl_price_proximity


def _make_fixture() -> pd.DataFrame:
    dates = pd.bdate_range("2020-01-01", periods=50)
    close = [110.0] * len(dates)
    close[13] = 101.2
    close[14] = 100.5
    close[15] = 100.0
    close[16] = 100.8
    close[17] = 101.1
    close[23:41] = [100.1] * 18
    return pd.DataFrame({
        "date": dates,
        "open": close,
        "high": [v + 0.5 for v in close],
        "low": [v - 0.5 for v in close],
        "close": close,
        "volume": 1_000_000,
    })


def test_spatial_gt_uses_price_distance() -> None:
    df = _make_fixture()
    gt = build_sl_price_gt(df, sl_n=7, pct=0.01)

    assert bool(gt.loc[14, "is_sl_price_gt"])
    assert bool(gt.loc[15, "is_sl_price_gt"])
    assert bool(gt.loc[16, "is_sl_price_gt"])
    assert not bool(gt.loc[13, "is_sl_price_gt"])
    assert not bool(gt.loc[17, "is_sl_price_gt"])
    # 即使价格接近旧底部，超出 SL7 自身定义窗口后也不能无限横向扩张。
    assert not bool(gt.loc[30, "is_sl_price_gt"])
    assert gt.loc[15, "price_quality"] == 1.0
    assert gt.loc[16, "price_quality"] < gt.loc[14, "price_quality"]
    assert gt.loc[15, "sl_distance"] == 0


def test_signal_filter_only_selects_samples() -> None:
    df = _make_fixture()
    signal = pd.Series(False, index=df.index)
    signal.loc[[13, 14, 15, 16, 17]] = True

    labeled = create_labels_sl_price_proximity(df, signal, sl_n=7, pct=0.01)
    labels = dict(zip(labeled["date"], labeled["label"]))

    assert labels[df.loc[13, "date"]] == 0
    assert labels[df.loc[14, "date"]] == 1
    assert labels[df.loc[15, "date"]] == 1
    assert labels[df.loc[16, "date"]] == 1
    assert labels[df.loc[17, "date"]] == 0


def test_invalid_spatial_threshold_is_rejected() -> None:
    df = _make_fixture()
    for pct in [0.0, 1.0]:
        try:
            build_sl_price_gt(df, sl_n=7, pct=pct)
        except ValueError:
            continue
        raise AssertionError(f"非法 pct 未被拒绝: {pct}")


if __name__ == "__main__":
    test_spatial_gt_uses_price_distance()
    test_signal_filter_only_selects_samples()
    test_invalid_spatial_threshold_is_rejected()
    print("[Test] 空间 GT 标注校验通过")
