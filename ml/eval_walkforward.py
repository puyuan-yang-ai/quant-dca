"""
Walk-Forward 评估编排:
  建数据(复用 train_export._build_dataset) → 扩展窗逐折训练/预测(含 purge/embargo + 唯一性权重)
  → 拼接全样本外概率 → 每折/整体 AUC + bootstrap 置信区间 → 存 OOS 概率 + 报告。
不训练/导出生产模型,不改 versions.py。
"""
import argparse
import importlib
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, average_precision_score

from ml.versions import get_active_config, ACTIVE_VERSION
from ml.train_export import _build_dataset, _make_model
from ml.walk_forward import make_expanding_folds, purge_embargo_mask, uniqueness_weights

OUTPUT_DIR = Path(__file__).parent.parent / "output"
HORIZON_DAYS = 28  # 见计划"关键约定"


def _bootstrap_auc_ci(y, proba, n_boot=2000, seed=42):
    """percentile bootstrap 95% CI(注:标签重叠会令 CI 略偏乐观,作近似诊断)。"""
    rng = np.random.default_rng(seed)
    y, proba = np.asarray(y), np.asarray(proba)
    n = len(y)
    aucs = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        if len(np.unique(y[idx])) < 2:
            continue
        aucs.append(roc_auc_score(y[idx], proba[idx]))
    if not aucs:
        return (float("nan"), float("nan"))
    return (float(np.percentile(aucs, 2.5)), float(np.percentile(aucs, 97.5)))


def run_walkforward(version=None, n_folds=4, min_train=None):
    version = version or ACTIVE_VERSION
    config = get_active_config()
    features_module = importlib.import_module(config["features_module"])
    method = config["labeling"]["method"]
    labeling_kwargs = {k: v for k, v in config["labeling"].items() if k != "method"}

    data, feature_cols = _build_dataset(method, features_module, **labeling_kwargs)
    data = data.sort_values("date").reset_index(drop=True)
    dates = pd.to_datetime(data["date"])
    X = data[feature_cols].values
    y = data["label"].values

    if min_train is None:
        min_train = max(20, int(len(data) * 0.4))  # 首折至少 40% 或 20 个样本
    folds = make_expanding_folds(dates, n_folds=n_folds, min_train=min_train)

    oos = data[["date", "label", "forward_return"]].copy()
    oos["proba"] = np.nan
    oos["fold_id"] = -1
    oos["fold_threshold"] = np.nan

    fold_aucs = []
    for fid, (train_idx, test_idx) in enumerate(folds):
        keep = np.asarray(purge_embargo_mask(dates.iloc[train_idx], dates.iloc[test_idx], HORIZON_DAYS))
        tr = train_idx[keep]
        if len(tr) < 10 or len(np.unique(y[tr])) < 2:
            print(f"[Fold {fid}] purge 后训练样本不足({len(tr)}),跳过")
            continue
        w = uniqueness_weights(dates.iloc[tr], HORIZON_DAYS)
        model = _make_model(config["model"])
        model.fit(X[tr], y[tr], sample_weight=w)
        proba_test = model.predict_proba(X[test_idx])[:, 1]

        oos.loc[test_idx, "proba"] = proba_test
        oos.loc[test_idx, "fold_id"] = fid
        # 折内阈值 = 训练集 proba 中位数(只看训练集,无目标偷看)
        thr = float(np.median(model.predict_proba(X[tr])[:, 1]))
        oos.loc[test_idx, "fold_threshold"] = thr

        yt = y[test_idx]
        if len(np.unique(yt)) > 1:
            a = roc_auc_score(yt, proba_test)
            fold_aucs.append((fid, a, int(len(yt))))
            print(f"[Fold {fid}] test={len(yt)} 信号  AUC={a:.3f}  阈值={thr:.3f}")
        else:
            print(f"[Fold {fid}] 测试集标签单一,AUC 跳过(test={len(yt)})")

    oos_valid = oos.dropna(subset=["proba"])
    yv, pv = oos_valid["label"].values, oos_valid["proba"].values
    overall_auc = float(roc_auc_score(yv, pv)) if len(np.unique(yv)) > 1 else float("nan")
    overall_pr = float(average_precision_score(yv, pv)) if len(np.unique(yv)) > 1 else float("nan")
    ci = _bootstrap_auc_ci(yv, pv)

    OUTPUT_DIR.mkdir(exist_ok=True)
    oos_csv_path = OUTPUT_DIR / f"oos_proba_{version}.csv"
    oos_valid.to_csv(oos_csv_path, index=False)

    print("\n" + "=" * 56)
    print("  Walk-Forward 样本外评估")
    print("=" * 56)
    print(f"  折数: {len(folds)}  拼接 OOS 样本: {len(oos_valid)}")
    print(f"  整体 AUC-ROC: {overall_auc:.4f}   95% CI: ({ci[0]:.4f}, {ci[1]:.4f})")
    print(f"  整体 AUC-PR:  {overall_pr:.4f}")
    print(f"  单折 AUC: " + ", ".join(f"f{fid}={a:.3f}(n={n})" for fid, a, n in fold_aucs))
    print(f"  [Output] {oos_csv_path}")
    print("=" * 56)

    return {
        "oos": oos_valid, "overall_auc": overall_auc, "overall_pr": overall_pr,
        "auc_ci": ci, "fold_aucs": fold_aucs, "oos_csv_path": str(oos_csv_path),
    }


def main():
    p = argparse.ArgumentParser(description="Walk-Forward 样本外评估")
    p.add_argument("--version", default=None)
    p.add_argument("--folds", type=int, default=4)
    args = p.parse_args()
    run_walkforward(version=args.version, n_folds=args.folds)


if __name__ == "__main__":
    main()
