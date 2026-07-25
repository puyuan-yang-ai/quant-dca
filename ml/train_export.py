"""
训练并导出模型 — 生产推理用

与 evaluate.py 的区别：
- evaluate.py 用于研究（80/20 切分、画对比图、不保存模型）
- 本脚本用于生产（全量数据训练、导出可复制的模型文件 + 元数据）

产出：
  models/spy_nday5_<version>.ubj    XGBoost 模型（二进制，跨平台可加载）
  models/spy_nday5_<version>.json   元数据（特征顺序、训练期、标注配置、评估指标）

使用：
  cd /home/puyuyang/workspace/projects/study/quant-dca
  python -m ml.train_export                 # 用 versions.py 激活版本，全量训练并导出
  python -m ml.train_export --holdout 0.2   # 留出最近 20% 做样本外评估后再全量训练导出

设计原则：
  推理脚本（predict.py）必须严格按元数据里的 feature_cols 顺序构造特征，
  否则列错位会导致预测完全失真。元数据是训练与推理之间的契约。
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score, average_precision_score
from xgboost import XGBClassifier

from ml.labeling import run as run_labeling, load_spy
from ml.versions import get_active_config, ACTIVE_VERSION

MODELS_DIR = Path(__file__).parent.parent / "models"


def _build_dataset(method: str, features_module, n_days: int = 5, signal_cfg: dict = None, **labeling_kwargs):
    """加载数据 → 生成信号 → 打标签 → 构造特征，返回 (data, feature_cols)

    n_days: NDay 信号门槛（连续低于 EMA20 的天数）。默认 5 向后兼容。
    signal_cfg: 初级信号配置（如 {'type':'nearbottom',...} 走路径A）。
    """
    labeled = run_labeling(n_days=n_days, method=method, signal_cfg=signal_cfg, **labeling_kwargs)
    spy_df = load_spy()
    data, feature_cols = features_module.build_features(labeled, spy_df)
    data = data.dropna(subset=feature_cols).reset_index(drop=True)
    print(f"[Dataset] 特征数: {len(feature_cols)}  有效样本: {len(data)}")
    return data, feature_cols


def _make_model(model_cfg: dict) -> XGBClassifier:
    return XGBClassifier(
        n_estimators=model_cfg.get("n_estimators", 100),
        max_depth=model_cfg.get("max_depth", 4),
        learning_rate=model_cfg.get("learning_rate", 0.1),
        eval_metric="logloss",
        random_state=42,
        verbosity=0,
    )


def train_and_export(version: str = None, holdout: float = 0.0, model_name: str = None) -> dict:
    """
    全量训练并导出模型 + 元数据。

    Args:
        version: 版本号（默认用 versions.py 的 ACTIVE_VERSION）
        holdout: 若 >0，先用前 (1-holdout) 训练、最近 holdout 评估，记录样本外指标；
                 评估完成后仍用【全量数据】重新训练并导出（生产模型应吃尽所有历史）。

    Returns:
        元数据字典
    """
    version = version or ACTIVE_VERSION
    from ml.versions import VERSIONS
    config = VERSIONS[version]  # 按传入版本取配置（而非固定 ACTIVE_VERSION）
    import importlib
    features_module = importlib.import_module(config["features_module"])

    method = config["labeling"]["method"]
    labeling_kwargs = {k: v for k, v in config["labeling"].items() if k != "method"}
    signal_cfg = config.get("signal", {})
    n_days = signal_cfg.get("n_days", 5)

    # 初级信号标签（用于文件名/元数据，避免近底信号被误标成 ndayN）
    if signal_cfg.get("type") == "nearbottom":
        sig_tag = f"nearbottom_n{int(signal_cfg.get('n', 20))}p{int(round(signal_cfg.get('pct', 0.03) * 100))}"
    else:
        sig_tag = f"nday{n_days}"

    data, feature_cols = _build_dataset(method, features_module, n_days=n_days,
                                        signal_cfg=signal_cfg, **labeling_kwargs)

    X = data[feature_cols].values
    y = data["label"].values
    dates = data["date"]

    # --- 样本外评估（可选）：用历史切分估计模型真实泛化能力 ---
    holdout_metrics = {}
    if holdout > 0:
        split_idx = int(len(data) * (1 - holdout))
        model_eval = _make_model(config["model"])
        model_eval.fit(X[:split_idx], y[:split_idx])
        proba = model_eval.predict_proba(X[split_idx:])[:, 1]
        y_test = y[split_idx:]
        if len(np.unique(y_test)) > 1:
            holdout_metrics = {
                "auc_roc": float(roc_auc_score(y_test, proba)),
                "auc_pr": float(average_precision_score(y_test, proba)),
                "test_pos_rate": float(y_test.mean()),
                "test_samples": int(len(y_test)),
                "test_period": [
                    dates.iloc[split_idx].strftime("%Y-%m-%d"),
                    dates.iloc[-1].strftime("%Y-%m-%d"),
                ],
            }
            print(f"[Holdout] 样本外 AUC-ROC={holdout_metrics['auc_roc']:.4f} "
                  f"AUC-PR={holdout_metrics['auc_pr']:.4f} "
                  f"(测试期 {holdout_metrics['test_period'][0]} ~ {holdout_metrics['test_period'][1]})")
        else:
            print("[Holdout] 测试集标签单一，跳过样本外评估")

    # --- 生产模型：用全量数据训练（推理时要用上所有历史信号） ---
    model = _make_model(config["model"])
    model.fit(X, y)
    print(f"[Train] 全量训练完成：{len(data)} 样本，{len(feature_cols)} 特征")

    MODELS_DIR.mkdir(exist_ok=True)
    # 模型名：优先用传入的 model_name(独特命名) → 否则 config.codename → 否则 spy_<sig_tag>_<version>
    name = model_name or config.get("codename") or f"spy_{sig_tag}_{version}"
    model_path = MODELS_DIR / f"{name}.ubj"
    meta_path = MODELS_DIR / f"{name}.json"

    model.save_model(str(model_path))

    importance = model.feature_importances_
    feature_importance = {
        col: float(imp) for col, imp in zip(feature_cols, importance)
    }

    meta = {
        "version": version,
        "model_name": name,
        "model_file": model_path.name,
        "target": f"SPY 底部识别：初级信号[{sig_tag}] + 标签[{method} {config['labeling']}]",
        "trained_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "features_module": config["features_module"],
        "signal": signal_cfg,
        "labeling": config["labeling"],
        "model_params": config["model"],
        # 推理契约：必须按此顺序构造特征列
        "feature_cols": feature_cols,
        "feature_importance": feature_importance,
        "n_train_samples": int(len(data)),
        "train_period": [
            dates.iloc[0].strftime("%Y-%m-%d"),
            dates.iloc[-1].strftime("%Y-%m-%d"),
        ],
        "train_pos_rate": float(y.mean()),
        "holdout_metrics": holdout_metrics,
    }

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"\n[Export] 模型已保存:   {model_path}")
    print(f"[Export] 元数据已保存: {meta_path}")
    print(f"[Export] 训练期: {meta['train_period'][0]} ~ {meta['train_period'][1]}")
    print(f"[Export] 正标签比例: {meta['train_pos_rate']:.1%}")

    # 打印 feature importance Top-10 便于快速核对
    top = sorted(feature_importance.items(), key=lambda kv: kv[1], reverse=True)[:10]
    print(f"\n[Feature Importance Top-10]")
    for name, imp in top:
        print(f"  {name:<28} {imp:.4f}")

    return meta


def main():
    parser = argparse.ArgumentParser(description="训练并导出生产推理模型")
    parser.add_argument("--version", type=str, default=None,
                        help="版本号（默认用 versions.py 的 ACTIVE_VERSION）")
    parser.add_argument("--holdout", type=float, default=0.0,
                        help="留出最近比例做样本外评估（如 0.2），仅记录指标，仍全量训练导出")
    parser.add_argument("--name", type=str, default=None,
                        help="自定义模型名（落盘文件名）；不传则用 config.codename 或 spy_<sig>_<version>")
    args = parser.parse_args()

    print("=" * 55)
    print("  训练并导出生产推理模型")
    print("=" * 55)
    train_and_export(version=args.version, holdout=args.holdout, model_name=args.name)
    print("\n" + "=" * 55)
    print("  完成。将 models/ 目录拷贝到 Mac mini 即可用 predict.py 推理。")
    print("=" * 55)


if __name__ == "__main__":
    main()
