# SOP：底部识别模型（当前 SOTA = v5_pa）— 从训练到评估

> 用途：把当前最优"识别低点"模型的**参数、逻辑、训练→评估全流程**固化为 SOP，
> 供后续设计实验 / 训模型时借鉴。当前 SOTA 由**检测 F1** 选出：v5_pa（F1 0.512）。

## 〇、五段式流水线（核心心智模型）

```
原始K线 → ①初级信号(候选universe) → ②标签(GT) → ③特征 → ④模型 → ⑤评估
            第一层过滤(因果)          打标签(可用未来)   per-day   XGBoost   WF + 检测P/R/F1
```
**杠杆优先级（实证）**：① universe ≈ ② 标签 ＞＞ ③ 特征。改 universe 让 F1 0.40→0.51；加 czsc 特征 ≈ 0。

## 一、当前 SOTA = v5_pa 的完整参数

| 环节 | 配置 |
|---|---|
| 标的/数据 | SPY 日线全周期（`data/SPY_adjusted.csv`，含成交量） |
| **① 初级信号(候选)** | **对称近底**：`收盘 ≤ 近 30 个交易bar 最低价 ×(1+0.05)`（因果，仅用过去）；SL7 两侧候选右/左≈1.03 |
| **② 标签(GT)** | `sl_proximity`，`sl_n=7`，`k=2`（**交易 bar 距离**）：候选日距最近 SL7 摆动低点 ≤2 bar → label=1 |
| **③ 特征** | `features_v3`：21 列（RSI/EMA距离/回撤/breadth/VIX regime/连续低于均线/各类布尔+窗口化+confluence） |
| **④ 模型** | XGBoost：`n_estimators=100, max_depth=4, learning_rate=0.1, eval_metric=logloss, seed=42` |
| 注册位置 | `ml/versions.py` 的 `v5_pa`（`signal={type:nearbottom,n:30,pct:0.05}`） |

> 关键认知：czsc 特征经多轮消融（离散/单布尔/5列）均无增益，**不纳入** SOTA。

## 二、各环节逻辑要点（设计实验时的原则）

- **① 初级信号必须因果**（实盘要用，不能偷看未来）。"近底"比"跌破均线"更聚焦真低位、更可学。**候选要比标签松**（否则 label≈常数、ML 无事可学）。
- **② 标签可用未来**（它是答案）。距离用**交易 bar**而非日历日，与系统其余口径统一。
- **③ 特征只加不减优先**；**不要机械正交精简**（实测精简反而掉点：被判"冗余"的列在交互里有用）。
- **④ 模型**保持小而稳（depth 4 防过拟合，样本量级千级）。
- **⑤ 评估**见下，必须**样本外 + 防泄漏**。

## 三、训练流程（落盘生产模型）

```bash
python -m ml.train_export --version v5_pa            # 全量训练并导出
python -m ml.train_export --version v5_pa --holdout 0.2   # 先留最近20%估泛化, 再全量训练导出
```
- 产出：`models/<模型名>.ubj`（XGBoost 二进制）+ `<模型名>.json`（**推理契约**：feature_cols 顺序、训练期、标注/信号配置、feature_importance、holdout 指标）。
- 原则：生产模型用**全量数据**训练（推理要吃尽所有历史信号）；holdout 仅用于估泛化、不作为最终模型。
- 推理（`ml/predict.py`）**必须严格按 meta 的 feature_cols 顺序**构造特征，否则列错位预测失真。

## 四、评估流程（两层 + 防泄漏）

**统计/检测层**（`ml/eval_walkforward.py` + `ml/research/eval_detection_pr.py`）
- **Walk-Forward**：扩展窗 4 折 + **Purge/Embargo(28天)** 防标签泄漏 + **样本唯一性权重**（重叠标签降权）。
- **AUC-ROC**（排序力，辅）；**Precision/Recall/F1**（检测任务主指标）。
- **公平口径**：全 K 线 + 共同 GT(SL7±2) 算 P/R/F1（见 `detection-pr-benchmark.md`）。

**经济层**（`ml/eval_economics.py`，需接交易系统，本阶段未做）
- OOS 概率 → Entry 过滤 → 标准化执行层回测 → 扣成本 Sharpe / 回撤 / 收益 + 阈值扫描。

**指标选择原则（重要）**
- "识别低点"=检测任务 → 用 **P/R/F1**（不是 IC，IC 量"信号 vs 收益"目标错配）。
- **精确率随机基准 = 正例占比**（不是 0.5）；**精确率不随分母变，召回率随口径变**。
- 横向可比性 = **统一 universe + 统一 GT 定义**；终极尺(赚不赚)= 扣成本样本外夏普（需交易系统）。

## 五、当前 SOTA 成绩（参考基线）

- 检测（全 K 线, 共同 GT=SL7±2, OOS 2005–2026）：**Precision ~0.52 / Recall ~0.57 / F1 0.512**（fold 阈值）；随机精确率基准 20.8%。
- 统计：WF AUC-ROC ≈ 0.752。

## 六、设计新实验的 Checklist（借鉴模板）

1. 一次只动一个变量（universe / 标签 / 特征 / 模型其一）。
2. 初级信号因果、且比标签松。
3. 标签明确（"是不是底" vs "赚不赚"——选对目标）。
4. 评估必走 WF + Purge/Embargo；检测任务报 P/R/F1，口径统一(全K线+共同GT)。
5. 不动 `ACTIVE_VERSION`，新版本先做实验，验证充分再上线。
6. 警惕：幸存者/前视偏差、准确率悖论、AUC 被易分负样本灌水、精确率基准=正例占比。

## 七、已知天花板与下一步

- **标签天花板**：`sl_proximity` 标"底部邻近度" ≠ "收益"。识别底准 ≠ 赚钱。
- **下一步破局**：换收益类标签（triple-barrier / 收益分位），让目标与收益对齐，再接经济层评估。
