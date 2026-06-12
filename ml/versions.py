"""
模型版本注册表

每个版本定义：标注方式 + 特征模块 + 模型参数
切换版本只需改 ACTIVE_VERSION。
"""

VERSIONS = {
    "v1": {
        "description": "SL7 Proximity 基准版 (2026-06-12)",
        "features_module": "ml.features_v1",
        "labeling": {
            "method": "sl_proximity",
            "sl_n": 7,
            "k": 3,
        },
        "model": {
            "n_estimators": 100,
            "max_depth": 4,
            "learning_rate": 0.1,
        },
        "metrics": {
            "auc_roc": 0.599,
            "auc_pr": 0.480,
            "ml_avg_20d_return": 0.0361,
            "ml_signal_count": 82,
            "baseline_avg_20d_return": 0.0216,
        },
    },
    "v2": {
        "description": "V2: V1全保留 + 4新特征(只加不减) (2026-06-12)",
        "features_module": "ml.features_v2",
        "labeling": {
            "method": "sl_proximity",
            "sl_n": 7,
            "k": 3,
        },
        "model": {
            "n_estimators": 100,
            "max_depth": 4,
            "learning_rate": 0.1,
        },
        "metrics": {
            "auc_roc": 0.618,
            "auc_pr": 0.472,
            "ml_avg_20d_return": 0.0316,
            "ml_signal_count": 85,
            "baseline_avg_20d_return": 0.0216,
        },
    },
    "v3": {
        "description": "V3: 窗口化+confluence (SL7 GT) (2026-06-12)",
        "features_module": "ml.features_v3",
        "labeling": {
            "method": "sl_proximity",
            "sl_n": 7,
            "k": 3,
        },
        "model": {
            "n_estimators": 100,
            "max_depth": 4,
            "learning_rate": 0.1,
        },
        "metrics": {},
    },
}

ACTIVE_VERSION = "v3"


def get_active_config() -> dict:
    """获取当前激活版本的配置"""
    return VERSIONS[ACTIVE_VERSION]


def list_versions():
    """列出所有版本及其核心指标"""
    print(f"{'版本':<6} {'描述':<40} {'AUC-ROC':>8} {'20D收益':>8} {'状态':<6}")
    print("-" * 75)
    for ver, cfg in VERSIONS.items():
        m = cfg.get("metrics", {})
        status = "★ 激活" if ver == ACTIVE_VERSION else ""
        print(f"{ver:<6} {cfg['description']:<40} "
              f"{m.get('auc_roc', 0):>8.3f} "
              f"{m.get('ml_avg_20d_return', 0)*100:>7.2f}% "
              f"{status}")
