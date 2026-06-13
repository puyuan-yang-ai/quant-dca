"""
模型训练 + 评估 + 可视化
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from xgboost import XGBClassifier
from scipy import stats
from sklearn.metrics import (
    roc_auc_score, average_precision_score, accuracy_score,
    precision_score, recall_score, log_loss, f1_score,
)

OUTPUT_DIR = Path(__file__).parent.parent / "output"


def train_and_evaluate(data: pd.DataFrame, feature_cols: list[str]) -> dict:
    """
    时间序列 80/20 切分 → XGBoost 训练 → 评估 + 可视化

    Returns:
        包含所有结果指标的字典
    """
    OUTPUT_DIR.mkdir(exist_ok=True)

    data = data.dropna(subset=feature_cols)
    split_idx = int(len(data) * 0.8)

    train = data.iloc[:split_idx]
    test = data.iloc[split_idx:]

    X_train = train[feature_cols].values
    y_train = train["label"].values
    X_test = test[feature_cols].values
    y_test = test["label"].values

    print(f"\n[Train/Test] 训练集: {len(train)} 样本, 测试集: {len(test)} 样本")
    print(f"[Train/Test] 训练集正标签比例: {y_train.mean():.1%}")
    print(f"[Train/Test] 测试集正标签比例: {y_test.mean():.1%}")
    print(f"[Train/Test] 训练期: {train['date'].iloc[0].strftime('%Y-%m-%d')} ~ {train['date'].iloc[-1].strftime('%Y-%m-%d')}")
    print(f"[Train/Test] 测试期: {test['date'].iloc[0].strftime('%Y-%m-%d')} ~ {test['date'].iloc[-1].strftime('%Y-%m-%d')}")

    model = XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.1,
        eval_metric="logloss",
        random_state=42,
        verbosity=0,
    )
    model.fit(X_train, y_train)

    proba = model.predict_proba(X_test)[:, 1]
    pred = (proba >= 0.5).astype(int)

    auc_roc = roc_auc_score(y_test, proba)
    auc_pr = average_precision_score(y_test, proba)
    logloss = log_loss(y_test, proba)
    acc = accuracy_score(y_test, pred)
    prec = precision_score(y_test, pred, zero_division=0)
    rec = recall_score(y_test, pred, zero_division=0)

    f1 = f1_score(y_test, pred, zero_division=0)

    print(f"\n{'='*50}")
    print(f"  XGBoost 模型评估 (测试集)")
    print(f"{'='*50}")
    print(f"  Precision:{prec:.4f}  ← 信号可信度")
    print(f"  Recall:   {rec:.4f}  ← 底部覆盖率")
    print(f"  F1-score: {f1:.4f}  ← 综合评分")
    print(f"  AUC-ROC:  {auc_roc:.4f}")
    print(f"  AUC-PR:   {auc_pr:.4f}")
    print(f"  Log Loss: {logloss:.4f}")
    print(f"{'='*50}")

    # --- 对比: 原始信号 vs ML 过滤后 ---
    test_returns = test["forward_return"].values

    baseline_win_rate = (test_returns > 0).mean()
    baseline_avg_ret = test_returns.mean()
    baseline_count = len(test_returns)

    ml_mask = proba >= 0.5
    if ml_mask.sum() > 0:
        ml_returns = test_returns[ml_mask]
        ml_win_rate = (ml_returns > 0).mean()
        ml_avg_ret = ml_returns.mean()
        ml_count = ml_mask.sum()
    else:
        ml_win_rate = ml_avg_ret = 0
        ml_count = 0

    # T-test: ML过滤后收益 vs baseline
    t_stat = p_value = 0.0
    if ml_mask.sum() > 5:
        skip_returns = test_returns[~ml_mask]
        if len(skip_returns) > 5:
            t_stat, p_value = stats.ttest_ind(ml_returns, skip_returns)

    print(f"\n{'='*50}")
    print(f"  信号质量对比 (测试集)")
    print(f"{'='*50}")
    print(f"  {'指标':<12} {'原始NDay5':<15} {'ML过滤后':<15}")
    print(f"  {'─'*42}")
    print(f"  {'信号数量':<12} {baseline_count:<15} {ml_count:<15}")
    print(f"  {'胜率':<12} {baseline_win_rate:<15.1%} {ml_win_rate:<15.1%}")
    print(f"  {'平均20D收益':<10} {baseline_avg_ret:<15.2%} {ml_avg_ret:<15.2%}")
    print(f"{'='*50}")
    print(f"  T-test (ML买入 vs ML跳过): t={t_stat:.3f}  p={p_value:.4f}  {'显著' if p_value < 0.05 else '不显著'}")
    print(f"{'='*50}")

    # --- 可视化 ---
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("ML Meta-Labeling MVP — NDay5 + XGBoost", fontsize=14, fontweight="bold")

    # 1) 概率分布
    ax = axes[0, 0]
    ax.hist(proba[y_test == 1], bins=20, alpha=0.6, label="Positive (win)", color="green")
    ax.hist(proba[y_test == 0], bins=20, alpha=0.6, label="Negative (loss)", color="red")
    ax.axvline(0.5, color="black", linestyle="--", label="Threshold=0.5")
    ax.set_xlabel("Predicted Probability")
    ax.set_ylabel("Count")
    ax.set_title("Probability Distribution by True Label")
    ax.legend()

    # 2) 累计收益对比
    ax = axes[0, 1]
    baseline_cum = np.cumsum(test_returns) * 100
    ml_cum_returns = np.where(ml_mask, test_returns, 0)
    ml_cum = np.cumsum(ml_cum_returns) * 100
    ax.plot(range(len(baseline_cum)), baseline_cum, label=f"Baseline NDay5 (n={baseline_count})", color="blue")
    ax.plot(range(len(ml_cum)), ml_cum, label=f"ML Filtered (n={ml_count})", color="green")
    ax.axhline(0, color="gray", linestyle="--", alpha=0.5)
    ax.set_xlabel("Signal Index (test set)")
    ax.set_ylabel("Cumulative Return (%)")
    ax.set_title("Cumulative Return Comparison")
    ax.legend()

    # 3) 特征重要度
    ax = axes[1, 0]
    importance = model.feature_importances_
    sorted_idx = np.argsort(importance)
    ax.barh(range(len(feature_cols)), importance[sorted_idx], color="steelblue")
    ax.set_yticks(range(len(feature_cols)))
    ax.set_yticklabels([feature_cols[i] for i in sorted_idx])
    ax.set_xlabel("Feature Importance")
    ax.set_title("XGBoost Feature Importance")

    # 4) 胜率对比柱状图
    ax = axes[1, 1]
    categories = ["Win Rate", "Avg 5d Return (%)"]
    baseline_vals = [baseline_win_rate * 100, baseline_avg_ret * 100]
    ml_vals = [ml_win_rate * 100, ml_avg_ret * 100]
    x = np.arange(len(categories))
    width = 0.35
    ax.bar(x - width / 2, baseline_vals, width, label="Baseline NDay5", color="blue", alpha=0.7)
    ax.bar(x + width / 2, ml_vals, width, label="ML Filtered", color="green", alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(categories)
    ax.set_title("Signal Quality Comparison")
    ax.legend()

    plt.tight_layout()
    output_path = OUTPUT_DIR / "ml_mvp_comparison.png"
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()

    print(f"\n[Output] 可视化已保存: {output_path}")

    return {
        "auc_roc": auc_roc, "auc_pr": auc_pr, "log_loss": logloss,
        "accuracy": acc, "precision": prec, "recall": rec, "f1": f1,
        "t_stat": t_stat, "t_test_p": p_value,
        "baseline_win_rate": baseline_win_rate, "ml_win_rate": ml_win_rate,
        "baseline_avg_return": baseline_avg_ret, "ml_avg_return": ml_avg_ret,
        "baseline_count": baseline_count, "ml_count": ml_count,
        "pos_rate": y_test.mean(),
        "output_path": str(output_path),
        "model": model, "test_data": test, "proba": proba,
    }
