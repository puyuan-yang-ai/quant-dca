# ML 模型版本管理方案

## 需求

- 支持多版本 ML 模型并存（v1, v2, v3...）
- 不同版本的特征集可能不同（代码级差异）
- 可以随时切换激活版本，一行代码回退
- 防止性能回退：新版本不好时不影响旧版本

## 目标

```
ml/
├── features_v1.py   ← v1 特征（锁定不动）
├── features_v2.py   ← v2 特征（未来新增）
├── versions.py      ← 版本注册表 + 切换开关
├── labeling.py      ← 共用（已支持多种标注方法）
├── evaluate.py      ← 共用
└── run_mvp.py       ← 共用（读 versions.py 决定用哪个特征模块）
```

## 实施方案

### Step 1: 重命名特征文件

```
features.py → features_v1.py
```

### Step 2: 更新 versions.py

在版本配置中指定特征模块：

```python
"v1": {
    "features_module": "ml.features_v1",
    ...
}
```

### Step 3: 修改 run_mvp.py

用 `importlib` 动态加载版本对应的特征模块：

```python
import importlib
from ml.versions import get_active_config

config = get_active_config()
features_mod = importlib.import_module(config["features_module"])
data, feature_cols = features_mod.build_features(labeled, spy_df)
```

### Step 4: 修改 show_chart.py

同样通过 versions.py 获取特征模块，不再硬编码 `from ml.features import ...`。

### Step 5: 回归测试

运行 `python -m ml.run_mvp --method sl_proximity`，确认结果与重构前一致：
- AUC-ROC ≈ 0.599
- ML 放行信号数 ≈ 82
- 平均 20D 收益 ≈ +3.61%

## 开发新版本的流程

```
1. 复制 features_v1.py → features_v2.py
2. 在 v2 中修改/新增特征
3. 在 versions.py 新增 "v2" 配置条目
4. 设置 ACTIVE_VERSION = "v2"，跑 pipeline
5. 对比 v1 和 v2 指标
6. v2 更好 → 保持；v2 不好 → ACTIVE_VERSION = "v1" 切回
```
