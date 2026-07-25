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
            "k": 2,  # 2026-06-28: GT 口径改为 SL7 ±2 交易bar
        },
        "signal": {
            "n_days": 5,
        },
        "model": {
            "n_estimators": 100,
            "max_depth": 4,
            "learning_rate": 0.1,
        },
        "metrics": {},
    },
    "v3_n2": {
        "description": "V3 配置 + NDay 门槛降为 2 (抓底诊断结论, 2026-06-26)",
        "features_module": "ml.features_v3",
        "labeling": {
            "method": "sl_proximity",
            "sl_n": 7,
            "k": 2,  # 2026-06-28: GT 口径改为 SL7 ±2 交易bar
        },
        # 信号门槛从 5 降到 2：诊断显示低门槛保留更多底部机会(Recall)，
        # 抓底质量与 N=5 基本一致。详见 docs/tasks/260626-ml-bottom-catch-diagnosis/
        "signal": {
            "n_days": 2,
        },
        "model": {
            "n_estimators": 100,
            "max_depth": 4,
            "learning_rate": 0.1,
        },
        "metrics": {},
    },
    "v4b": {
        "description": "V4b: v3_n2 + 单布尔 czsc_buy_today (2026-06-28)",
        "features_module": "ml.features_v4b",
        "labeling": {
            "method": "sl_proximity",
            "sl_n": 7,
            "k": 2,  # 2026-06-28: GT 口径改为 SL7 ±2 交易bar
        },
        "signal": {
            "n_days": 2,
        },
        "model": {
            "n_estimators": 100,
            "max_depth": 4,
            "learning_rate": 0.1,
        },
        "metrics": {},
    },
    "v4": {
        "description": "V4: v3_n2 + czsc 缠论特征(5列, 只加不减) (2026-06-28)",
        "features_module": "ml.features_v4",
        "labeling": {
            "method": "sl_proximity",
            "sl_n": 7,
            "k": 2,  # 2026-06-28: GT 口径改为 SL7 ±2 交易bar
        },
        # 与 v3_n2 完全一致的候选门槛与标签，唯一变量 = 附加 czsc 5 列特征
        "signal": {
            "n_days": 2,
        },
        "model": {
            "n_estimators": 100,
            "max_depth": 4,
            "learning_rate": 0.1,
        },
        "metrics": {},
    },
    "v5_pa": {
        "description": "V5(路径A,A0基线): 对称近底(距近30日低≤5%) + features_v3 (2026-06-29)",
        "features_module": "ml.features_v3",
        "labeling": {
            "method": "sl_proximity",
            "sl_n": 7,
            "k": 2,
        },
        # 路径 A：保留 meta-labeling，初级信号从 NDay 改为对称"近底"规则
        # N=30/pct=0.05：实测 SL7 两侧候选 右/左≈1.03（大体对称）
        "signal": {
            "type": "nearbottom",
            "n": 30,
            "pct": 0.05,
        },
        "model": {
            "n_estimators": 100,
            "max_depth": 4,
            "learning_rate": 0.1,
        },
        "metrics": {},
    },
    # ── 路径A czsc 消融臂（全部同 universe(近底n30p05) + 同标签(sl_proximity k2) ）──
    "v5_pa_c1": {  # A1: base + czsc 单布尔
        "description": "V5路径A 消融A1: 近底 + czsc单布尔(22列)",
        "features_module": "ml.features_v4b",
        "labeling": {"method": "sl_proximity", "sl_n": 7, "k": 2},
        "signal": {"type": "nearbottom", "n": 30, "pct": 0.05},
        "model": {"n_estimators": 100, "max_depth": 4, "learning_rate": 0.1},
        "metrics": {},
    },
    "v5_pa_c5": {  # A2: base + czsc 5 列
        "description": "V5路径A 消融A2: 近底 + czsc 5列(26列)",
        "features_module": "ml.features_v4",
        "labeling": {"method": "sl_proximity", "sl_n": 7, "k": 2},
        "signal": {"type": "nearbottom", "n": 30, "pct": 0.05},
        "model": {"n_estimators": 100, "max_depth": 4, "learning_rate": 0.1},
        "metrics": {},
    },
    "v5_pa_orth": {  # A3: 正交精简 base + czsc 5 列
        "description": "V5路径A 消融A3: 近底 + 正交精简base + czsc 5列",
        "features_module": "ml.features_v5_orth",
        "labeling": {"method": "sl_proximity", "sl_n": 7, "k": 2},
        "signal": {"type": "nearbottom", "n": 30, "pct": 0.05},
        "model": {"n_estimators": 100, "max_depth": 4, "learning_rate": 0.1},
        "metrics": {},
    },
}

ACTIVE_VERSION = "v3_n2"


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
