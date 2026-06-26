# 择时模型评估体系重做 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: 用 superpowers:subagent-driven-development(推荐)或 superpowers:executing-plans 逐任务执行。步骤用 `- [ ]` 复选框跟踪。
>
> 配套:设计依据见 `eval-overhaul-plan.md`;概念学习见 `auc-knowledge.md`。

**Goal:** 把"单次 80/20 切分、易泄漏"的评估,换成"扩展窗 Walk-Forward + Purge/Embargo + 标签去重"的量具,并在其上读出"AUC+置信区间"与"接引擎 A vs B 的经济指标",判断 SPY meta-label 择时模型是否有真信号。

**Architecture:** 纯逻辑(切分/防泄漏/权重)抽到 `ml/walk_forward.py`;编排(产出样本外概率 + AUC/CI)在 `ml/eval_walkforward.py`;模型过滤器作为一个新增 Entry 类接入现有引擎路径;经济回测(A vs B + 阈值)在 `ml/eval_economics.py`。全部只增不改,不碰生产链路(`predict.py`/`versions.py`/`train_export.py`)。

**Tech Stack:** Python、pandas/numpy、xgboost、scikit-learn、scipy;复用 `ml/labeling.py`、`ml/train_export._build_dataset`、`src/backtest_engine.py`、`src/strategies/composable.py`、`src/modules/*`。

---

## 测试约定(重要)

本仓库**无 pytest 框架**(CLAUDE.md 明确)。为不引入新依赖,纯逻辑单元测试写成**独立的 `assert` 脚本**,用 `python tests_eval/<name>.py` 直接运行,打印 `OK` 即通过。编排/出图类任务无法纯单测,用"运行 + 肉眼核对产出"验证(每步给出预期输出描述)。

---

## 文件结构(先锁定边界)

| 动作 | 文件 | 职责 |
| --- | --- | --- |
| 新增 | `ml/walk_forward.py` | 纯逻辑:扩展窗折切分、purge/embargo 掩码、样本唯一性权重 |
| 新增 | `ml/eval_walkforward.py` | 编排:建数据→跑 WF→拼接 OOS 概率→每折/整体 AUC+bootstrap CI→存 `output/oos_proba_<ver>.csv` + 报告 |
| 修改(纯追加) | `src/modules/entry.py` | 末尾**新增**一个 `OOSProbaEntry` 类;不改任何现有类 |
| 新增 | `ml/eval_economics.py` | 编排:读 OOS 概率→A vs B 接引擎→条件收益/Expectancy/t 检验→阈值扫描→出图+报告 |
| 新增 | `tests_eval/` | 三个 assert 测试脚本 |
| 新增 | `docs/tasks/260620-xxy/eval-conclusion.md` | 最终结论(任务 6 产出) |
| **不动** | `ml/predict.py` / `ml/versions.py` / `ml/train_export.py` / `ml/evaluate.py` | 生产与既有研究链路保持原样 |

> 说明:spec 原写"在 `src/modules/entry/` 下新增模块",但本仓库 entry 是单文件 `entry.py`、所有 Entry 类都集中在此。为遵循既有约定,改为在 `entry.py` **纯追加**一个类(不触碰现有类),等价满足"只增不改"。

---

## 关键约定(所有任务共用)

- **防泄漏 horizon = 28 个日历天**。理由:`sl_proximity` 标签需未来 ~7 个交易日确认 swing low,而 `forward_return` 取 **20 个交易日**远期;取两者最大(20 交易日 ≈ 28 日历天)最安全。
- **标准化执行层(照搬 `scripts/compare_signals.py:34-36`)**:
  ```python
  FixedTiers(drops=(0.02, 0.05, 0.10))            # 档位值不影响结果(limit_shares 全 0)
  FixedPyramid(market_shares=1, limit_shares=(0, 0, 0))
  NoTakeProfit()
  ```
- **A vs B 定义**:A = `NDayConfirmEntry(n_days=5)`(全 NDay5 信号);B = `OOSProbaEntry(pass_dates)`(NDay5 信号中模型放行的子集)。因 `pass_dates` 由信号日 + 模型概率筛出,天然是 NDay5 的子集。
- **日期对齐风险(必查)**:引擎 `load_data` 读 `DATA_FILE`(列头 `时间`),ML 读 `data/SPY_adjusted.csv`,**两个文件日期字符串格式可能不同**。`pass_dates` 必须转成引擎 `day['date']` 的格式;任务 5 含强制自检。

---

## Task 1: 纯逻辑模块 `ml/walk_forward.py`

**Files:**
- Create: `ml/walk_forward.py`
- Test: `tests_eval/test_walk_forward.py`

- [ ] **Step 1: 写失败测试**

```python
# tests_eval/test_walk_forward.py
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
```

- [ ] **Step 2: 运行确认失败**

Run: `python tests_eval/test_walk_forward.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'ml.walk_forward'`

- [ ] **Step 3: 写最小实现**

```python
# ml/walk_forward.py
"""Walk-Forward 评估的纯逻辑:扩展窗切分 + Purge/Embargo + 样本唯一性权重。"""
import numpy as np
import pandas as pd


def make_expanding_folds(dates, n_folds=4, min_train=20):
    """
    扩展窗(anchored)切分:训练集起点固定、逐折延长。
    把"测试区"(min_train 之后的样本)等分成 n_folds 段连续 chunk;
    第 i 折 train = 该 chunk 之前的全部样本,test = 该 chunk。

    Args:
        dates: 按时间升序的样本日期 Series(索引 0..N-1)
    Returns:
        [(train_idx ndarray, test_idx ndarray), ...]
    """
    n = len(dates)
    if min_train >= n:
        raise ValueError(f"min_train({min_train}) >= 样本数({n}),样本太少")
    test_region = np.arange(min_train, n)
    chunks = np.array_split(test_region, n_folds)
    folds = []
    for chunk in chunks:
        if len(chunk) == 0:
            continue
        test_idx = chunk
        train_idx = np.arange(0, test_idx.min())
        folds.append((train_idx, test_idx))
    return folds


def purge_embargo_mask(train_dates, test_dates, horizon_days=28):
    """
    返回训练集布尔掩码(True=保留)。
    剔除"标签窗口伸进测试期 / 落在测试期前 embargo 缓冲内"的训练样本:
    即 train_date + horizon_days >= test_start 的样本被剔除。
    horizon_days 同时承担 purge(标签重叠)与 embargo(特征自相关缓冲)。
    """
    train_dates = pd.to_datetime(pd.Series(train_dates).values)
    test_start = pd.to_datetime(pd.Series(test_dates).values).min()
    cutoff = test_start - pd.Timedelta(days=horizon_days)
    return (train_dates <= cutoff)


def uniqueness_weights(dates, horizon_days=28):
    """
    样本唯一性权重(López de Prado 简化版):
    每个样本的标签窗口 = [date, date+horizon_days]。
    权重 = 1 / (与该样本标签窗口重叠的样本数),归一化到 (0, 1]。
    重叠越多 → 越"虚胖" → 权重越低。
    """
    d = pd.to_datetime(pd.Series(dates).reset_index(drop=True))
    h = pd.Timedelta(days=horizon_days)
    n = len(d)
    overlap_count = np.ones(n)
    for i in range(n):
        start_i, end_i = d[i], d[i] + h
        overlap = ((d <= end_i) & (d + h >= start_i)).sum()
        overlap_count[i] = overlap
    w = 1.0 / overlap_count
    return w / w.max()
```

- [ ] **Step 4: 运行确认通过**

Run: `python tests_eval/test_walk_forward.py`
Expected: PASS — 打印 `OK`

- [ ] **Step 5: 提交**

```bash
git add ml/walk_forward.py tests_eval/test_walk_forward.py
git commit -m "feat: 新增 Walk-Forward 纯逻辑(扩展窗切分+purge/embargo+唯一性权重)"
```

---

## Task 2: WF 评估编排 `ml/eval_walkforward.py`

**Files:**
- Create: `ml/eval_walkforward.py`
- Test: `tests_eval/test_eval_walkforward_smoke.py`(冒烟:跑真实数据,校验产出结构)

- [ ] **Step 1: 写失败测试(冒烟)**

```python
# tests_eval/test_eval_walkforward_smoke.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ml.eval_walkforward import run_walkforward

def test_run_walkforward_outputs():
    res = run_walkforward(n_folds=4)
    assert "oos" in res and "overall_auc" in res and "auc_ci" in res
    oos = res["oos"]
    for col in ["date", "label", "forward_return", "proba", "fold_id", "fold_threshold"]:
        assert col in oos.columns, f"缺列 {col}"
    assert oos["proba"].between(0, 1).all()
    assert 0.0 <= res["overall_auc"] <= 1.0
    lo, hi = res["auc_ci"]
    assert lo <= res["overall_auc"] <= hi
    assert os.path.exists(res["oos_csv_path"])
    print("OK", "overall_auc=%.3f CI=(%.3f,%.3f) n=%d" %
          (res["overall_auc"], lo, hi, len(oos)))

if __name__ == "__main__":
    test_run_walkforward_outputs()
```

- [ ] **Step 2: 运行确认失败**

Run: `python tests_eval/test_eval_walkforward_smoke.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'ml.eval_walkforward'`

- [ ] **Step 3: 写实现**

```python
# ml/eval_walkforward.py
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
        keep = purge_embargo_mask(dates.iloc[train_idx], dates.iloc[test_idx], HORIZON_DAYS)
        tr = train_idx[keep.values]
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
```

- [ ] **Step 4: 运行确认通过**

Run: `python tests_eval/test_eval_walkforward_smoke.py`
Expected: PASS — 打印 `OK overall_auc=... CI=(...) n=...`;`output/oos_proba_v3.csv` 生成。
**若报样本不足/折太多导致某折标签单一**:把 `--folds` 调到 3 重试,并在结论里记录该限制(对应 spec 阶段 0 闸门)。

- [ ] **Step 5: 提交**

```bash
git add ml/eval_walkforward.py tests_eval/test_eval_walkforward_smoke.py
git commit -m "feat: Walk-Forward 评估编排(拼接OOS概率+整体AUC+bootstrap CI)"
```

---

## Task 3: 新增 `OOSProbaEntry`(纯追加到 entry.py)

**Files:**
- Modify: `src/modules/entry.py`(文件末尾追加一个类,不改现有类)
- Test: `tests_eval/test_oos_proba_entry.py`

- [ ] **Step 1: 写失败测试**

```python
# tests_eval/test_oos_proba_entry.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.modules.entry import OOSProbaEntry

class _Ctx:
    def __init__(self, date): self.day = {"date": date}

def test_oos_proba_entry_membership():
    e = OOSProbaEntry(pass_dates=["2020-03-23", "2020-03-24"])
    assert e.should_market_buy(_Ctx("2020-03-23")) is True
    assert e.should_market_buy(_Ctx("2020-01-01")) is False
    assert e.should_place_limits(_Ctx("2020-03-23")) is False

if __name__ == "__main__":
    test_oos_proba_entry_membership()
    print("OK")
```

- [ ] **Step 2: 运行确认失败**

Run: `python tests_eval/test_oos_proba_entry.py`
Expected: FAIL — `ImportError: cannot import name 'OOSProbaEntry'`

- [ ] **Step 3: 在 `src/modules/entry.py` 末尾追加**

```python
class OOSProbaEntry:
    """
    模型样本外概率过滤入场

    传入"模型放行的信号日日期集合"(已是 NDay5 信号 ∩ 概率>阈值 的子集),
    当天日期命中即市价买入。用于经济回测中的 B 组(NDay5 + 模型过滤)。
    日期字符串格式必须与引擎 day['date'] 一致(见调用方做对齐转换)。
    """

    def __init__(self, pass_dates):
        self._buy_dates = set(pass_dates)

    def should_market_buy(self, context):
        return context.day['date'] in self._buy_dates

    def should_place_limits(self, context):
        return False

    def __repr__(self):
        return f"OOSProbaEntry(signals={len(self._buy_dates)})"
```

- [ ] **Step 4: 运行确认通过**

Run: `python tests_eval/test_oos_proba_entry.py`
Expected: PASS — 打印 `OK`

- [ ] **Step 5: 提交**

```bash
git add src/modules/entry.py tests_eval/test_oos_proba_entry.py
git commit -m "feat: 新增 OOSProbaEntry(模型样本外概率过滤入场)"
```

---

## Task 4: 经济回测 `ml/eval_economics.py`(接引擎 A vs B)

**Files:**
- Create: `ml/eval_economics.py`
- Test: `tests_eval/test_eval_economics_smoke.py`

> 依赖 Task 2 已产出 `output/oos_proba_<ver>.csv`。

- [ ] **Step 1: 写失败测试(冒烟)**

```python
# tests_eval/test_eval_economics_smoke.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ml.eval_economics import run_economics

def test_run_economics_outputs():
    res = run_economics()
    for k in ["engine_A", "engine_B_foldinternal", "engine_B_05",
              "conditional", "sweep"]:
        assert k in res, f"缺 {k}"
    for grp in ["engine_A", "engine_B_foldinternal", "engine_B_05"]:
        for m in ["sharpe_ratio", "max_drawdown", "total_return"]:
            assert m in res[grp], f"{grp} 缺 {m}"
    c = res["conditional"]
    for m in ["e_pass", "e_skip", "e_all", "expectancy", "t_stat", "t_p"]:
        assert m in c
    assert len(res["sweep"]) >= 5  # 阈值曲线点数
    print("OK A_sharpe=%.3f Bfi_sharpe=%.3f" %
          (res["engine_A"]["sharpe_ratio"], res["engine_B_foldinternal"]["sharpe_ratio"]))

if __name__ == "__main__":
    test_run_economics_outputs()
```

- [ ] **Step 2: 运行确认失败**

Run: `python tests_eval/test_eval_economics_smoke.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'ml.eval_economics'`

- [ ] **Step 3: 写实现**

```python
# ml/eval_economics.py
"""
经济回测:把 Walk-Forward 拼接的样本外概率包装成 Entry 过滤器,接 backtest_engine
跑 A(NDay5 全信号) vs B(NDay5 + 模型过滤),用标准化执行层。
读数:扣成本 Sharpe / 回撤 / 总收益、条件收益差、Expectancy、收益差 t 检验、阈值扫描曲线。
不改任何现有文件。
"""
import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats

from src.data_loader import load_data
from src.backtest_engine import BacktestEngine
from src.strategies.composable import ComposableStrategy
from src.modules.tiers import FixedTiers
from src.modules.position import FixedPyramid
from src.modules.take_profit import NoTakeProfit
from src.modules.entry import NDayConfirmEntry, OOSProbaEntry
from experiments.configs import DATA_FILE, SMH_FILE, FEE_RATE
from ml.versions import ACTIVE_VERSION

ROOT = Path(__file__).parent.parent
OUTPUT_DIR = ROOT / "output"

# 标准化执行层(照搬 scripts/compare_signals.py)
STD_TIERS = FixedTiers(drops=(0.02, 0.05, 0.10))
STD_POSITION = FixedPyramid(market_shares=1, limit_shares=(0, 0, 0))
STD_TP = NoTakeProfit()


def _engine_date_format_sample():
    """返回引擎 DATA_FILE 的首个 day['date'] 字符串,用于核对格式。"""
    data = load_data(str(ROOT / DATA_FILE))
    return data[0]["date"] if data else None


def _to_engine_date_strings(dates):
    """把 OOS 概率表的日期转成引擎 day['date'] 用的字符串格式。
    引擎 DATA_FILE 日期形如 'YYYY-MM-DD'(纯日期);若实测不同,在此调整。"""
    return pd.to_datetime(pd.Series(dates)).dt.strftime("%Y-%m-%d").tolist()


def _run_engine(entry, start, end):
    data = load_data(str(ROOT / DATA_FILE), start, end)
    smh = load_data(str(ROOT / SMH_FILE), start, end)
    strat = ComposableStrategy(tiers=STD_TIERS, entry=entry,
                               position=STD_POSITION, take_profit=STD_TP)
    return BacktestEngine(data, smh, FEE_RATE, strat).run()


def run_economics(version=None):
    version = version or ACTIVE_VERSION
    oos_csv = OUTPUT_DIR / f"oos_proba_{version}.csv"
    if not oos_csv.exists():
        raise FileNotFoundError(f"先跑 ml.eval_walkforward 生成 {oos_csv}")
    oos = pd.read_csv(oos_csv, parse_dates=["date"])

    # OOS 回测区间
    start = oos["date"].min().strftime("%Y-%m-%d")
    end = oos["date"].max().strftime("%Y-%m-%d")

    # --- 日期对齐自检(关键)---
    eng_sample = _engine_date_format_sample()
    oos_strs = _to_engine_date_strings(oos["date"])
    eng_dates = {d["date"] for d in load_data(str(ROOT / DATA_FILE), start, end)}
    hit = len(set(oos_strs) & eng_dates)
    print(f"[对齐自检] 引擎日期样例={eng_sample!r}  OOS日期样例={oos_strs[0]!r}  "
          f"命中 {hit}/{len(oos_strs)}")
    if hit == 0:
        raise RuntimeError("OOS 日期与引擎日期零命中:格式不一致,请修正 _to_engine_date_strings")

    # --- 构造 pass_dates ---
    pass_fi = oos[oos["proba"] > oos["fold_threshold"]]["date"]
    pass_05 = oos[oos["proba"] > 0.5]["date"]
    pass_fi_strs = _to_engine_date_strings(pass_fi)
    pass_05_strs = _to_engine_date_strings(pass_05)

    # --- 三组引擎回测 ---
    eng_A = _run_engine(NDayConfirmEntry(n_days=5), start, end)
    eng_Bfi = _run_engine(OOSProbaEntry(pass_fi_strs), start, end)
    eng_B05 = _run_engine(OOSProbaEntry(pass_05_strs), start, end)

    def pick(m):
        return {"sharpe_ratio": m["sharpe_ratio"], "max_drawdown": m["max_drawdown"],
                "total_return": m["total_return"], "calmar_ratio": m["calmar_ratio"],
                "buy_count": m.get("buy_count", 0)}

    # --- 条件收益(事件研究)---
    fr = oos["forward_return"].values
    is_pass = (oos["proba"] > oos["fold_threshold"]).values
    e_pass = float(fr[is_pass].mean()) if is_pass.sum() else float("nan")
    e_skip = float(fr[~is_pass].mean()) if (~is_pass).sum() else float("nan")
    e_all = float(fr.mean())
    # Expectancy(按打/不打的 20日远期收益)
    win = fr[is_pass]
    expectancy = float(win.mean()) if len(win) else float("nan")
    if is_pass.sum() > 5 and (~is_pass).sum() > 5:
        t_stat, t_p = stats.ttest_ind(fr[is_pass], fr[~is_pass])
    else:
        t_stat, t_p = 0.0, 1.0

    # --- 阈值扫描 ---
    sweep = []
    for thr in np.round(np.arange(0.30, 0.71, 0.05), 2):
        pd_dates = _to_engine_date_strings(oos[oos["proba"] > thr]["date"])
        if not pd_dates:
            sweep.append({"thr": float(thr), "n": 0, "sharpe": float("nan"),
                          "e_fwd": float("nan")})
            continue
        m = _run_engine(OOSProbaEntry(pd_dates), start, end)
        mask = (oos["proba"] > thr).values
        sweep.append({"thr": float(thr), "n": int(mask.sum()),
                      "sharpe": float(m["sharpe_ratio"]),
                      "e_fwd": float(oos["forward_return"].values[mask].mean())})

    # --- 出图 ---
    OUTPUT_DIR.mkdir(exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle(f"经济回测 A vs B (OOS {start}~{end})", fontsize=13, fontweight="bold")
    ax = axes[0]
    ax.plot(eng_A["dates"], eng_A["daily_values"], label=f"A 全NDay5 (买{eng_A.get('buy_count',0)})")
    ax.plot(eng_Bfi["dates"], eng_Bfi["daily_values"], label=f"B 折内阈值 (买{eng_Bfi.get('buy_count',0)})")
    ax.plot(eng_B05["dates"], eng_B05["daily_values"], label=f"B 阈值0.5 (买{eng_B05.get('buy_count',0)})")
    ax.set_title("权益曲线"); ax.legend(); ax.set_xticks([])
    ax = axes[1]
    sdf = pd.DataFrame(sweep)
    ax.plot(sdf["thr"], sdf["sharpe"], marker="o", color="steelblue", label="Sharpe")
    ax.set_xlabel("阈值"); ax.set_ylabel("Sharpe"); ax.set_title("阈值扫描")
    ax2 = ax.twinx(); ax2.bar(sdf["thr"], sdf["n"], width=0.02, alpha=0.3, color="gray")
    ax2.set_ylabel("信号数")
    plt.tight_layout()
    plot_path = OUTPUT_DIR / f"eval_economics_{version}.png"
    plt.savefig(plot_path, dpi=150, bbox_inches="tight"); plt.close()

    # --- 打印报告 ---
    print("\n" + "=" * 60)
    print(f"  经济回测 A vs B (OOS {start} ~ {end})")
    print("=" * 60)
    print(f"  {'组':<22}{'Sharpe':>9}{'MaxDD':>9}{'总收益':>9}{'买入数':>8}")
    for name, m in [("A 全NDay5", eng_A), ("B 折内阈值", eng_Bfi), ("B 阈值0.5", eng_B05)]:
        print(f"  {name:<22}{m['sharpe_ratio']:>9.2f}{m['max_drawdown']*100:>8.1f}%"
              f"{m['total_return']*100:>8.1f}%{m.get('buy_count',0):>8}")
    print("-" * 60)
    print(f"  条件20日收益: 打={e_pass*100:+.2f}%  不打={e_skip*100:+.2f}%  全打={e_all*100:+.2f}%")
    print(f"  收益差 t={t_stat:.2f} p={t_p:.4f} {'显著' if t_p<0.05 else '不显著'}")
    print(f"  [Output] {plot_path}")
    print("=" * 60)

    return {
        "engine_A": pick(eng_A), "engine_B_foldinternal": pick(eng_Bfi),
        "engine_B_05": pick(eng_B05),
        "conditional": {"e_pass": e_pass, "e_skip": e_skip, "e_all": e_all,
                        "expectancy": expectancy, "t_stat": float(t_stat), "t_p": float(t_p)},
        "sweep": sweep, "plot_path": str(plot_path), "period": [start, end],
    }


def main():
    p = argparse.ArgumentParser(description="经济回测 A vs B")
    p.add_argument("--version", default=None)
    args = p.parse_args()
    run_economics(version=args.version)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行确认通过**

Run: `python tests_eval/test_eval_economics_smoke.py`
Expected: PASS — 打印 `OK A_sharpe=... Bfi_sharpe=...`;`output/eval_economics_v3.png` 生成。
**若 `[对齐自检]` 报零命中**:说明 `DATA_FILE` 日期格式不是 `YYYY-MM-DD`,按实测样例修正 `_to_engine_date_strings` 后重跑(这是计划"日期对齐风险"的落点)。

- [ ] **Step 5: 提交**

```bash
git add ml/eval_economics.py tests_eval/test_eval_economics_smoke.py
git commit -m "feat: 经济回测 A vs B(接引擎+条件收益+Expectancy+阈值扫描)"
```

---

## Task 5: 端到端跑通 + 结论沉淀

**Files:**
- Create: `docs/tasks/260620-xxy/eval-conclusion.md`

- [ ] **Step 1: 完整跑一遍**

Run:
```bash
python -m ml.eval_walkforward --folds 4
python -m ml.eval_economics
```
Expected: 两步均无异常;`output/oos_proba_v3.csv`、`output/eval_economics_v3.png` 生成;终端打印整体 AUC+CI、单折 AUC、A vs B 三组指标、条件收益与 t 检验。
**若 folds=4 某折标签单一**:改用 `--folds 3` 重跑并在结论中记录。

- [ ] **Step 2: 按验收判据写结论**

把实跑数字填进 `eval-conclusion.md`,逐条对照 spec 的三条判据:
1. 拼接 OOS AUC 的 CI 下沿是否明显 > 0.5、各折是否未崩塌。
2. 阈值扫描里 B 是否在一大片阈值(0.45~0.65)稳定优于 A,而非单尖峰。
3. B(折内阈值)的扣成本 Sharpe/回撤是否优于 A,且条件收益差 t 检验是否显著。

结论模板:
```markdown
# 评估结论(WF + 经济回测)
- 数据:OOS 样本 N=__,期 __~__,折数 __
- 统计:整体 AUC=__ CI=(__,__);单折 AUC=__
- 经济:A Sharpe=__ MaxDD=__ | B(折内) Sharpe=__ MaxDD=__ | B(0.5) Sharpe=__
- 条件20日收益:打=__ 不打=__ 全打=__;t=__ p=__
- 阈值稳健性:B 优于 A 的阈值区间 = __(连续区间/单尖峰)
- 判据对照:① __  ② __  ③ __
- 裁决:【保留迭代 / 这版废掉重做】+ 一句话理由
```

- [ ] **Step 3: 提交**

```bash
git add docs/tasks/260620-xxy/eval-conclusion.md output/oos_proba_v3.csv output/eval_economics_v3.png
git commit -m "docs: 沉淀 Walk-Forward + 经济回测评估结论"
```

---

## 自检(写完计划后核对 spec)

- **覆盖**:D1 重量级引擎(Task 4)、D2 标准化执行层+A/B(Task 4 常量与定义)、D3 拼接 OOS(Task 2)、D4 三阈值法(Task 4:折内/0.5/扫描)、D5 扩展窗(Task 1 `make_expanding_folds`)、D6 只增不改(文件表)——全部有落点。
- **占位符**:无 TBD;唯一运行期未知是 `DATA_FILE` 日期格式,已用"对齐自检 + 修正点"显式处理。
- **类型一致**:`run_walkforward` 产出列(date/label/forward_return/proba/fold_id/fold_threshold)与 `eval_economics` 消费列一致;`OOSProbaEntry(pass_dates)` 签名 Task 3 定义、Task 4 调用一致;标准化执行层三件套与 `compare_signals.py` 一致。

---

## 执行交接

计划完成。两种执行方式:

1. **Subagent-Driven(推荐)** — 每个 Task 派新 subagent,任务间审查,快速迭代。
2. **Inline 执行** — 本会话内用 executing-plans 分批执行,设检查点。

选哪个?
