# 任务：SPY 底部信号模型上线自动化（每日推理 + 报告 + 推送）

## 需求来源

模型研究阶段已结束，得到一个 XGBoost Meta-Labeling 模型（判断 SPY 的 NDay5 回踩信号是否处于底部区域）。用户希望把整条流程从"研究"推进到"投入使用"：部署到家里的 Mac mini，每天自动拉取最新数据、运行推理、产出预测报告，分析依据来自模型的 feature importance 等数据。

用户清楚该模型效果一般（样本外 AUC-ROC≈0.66，弱信号），但目标是**先打通工程闭环**，模型质量可后续迭代替换。

## 目标

1. **训练/推理分离**：训练在开发机做（重、偶尔做），推理在 Mac mini 做（轻、每天做）。模型作为文件随代码走。
2. **每日自动化**：Mac mini 每天定时执行「拉数据 → 推理 → 出报告 → 推送通知」。
3. **报告产出**：Markdown 格式的每日预测报告，含预测概率、是否信号日、feature importance、各特征当前值、数据新鲜度。
4. **通知**：通过 Telegram 推送到手机。

## 已明确的决策（与用户对齐）

| 项 | 决策 |
| --- | --- |
| 部署目标 | 家庭 Mac mini |
| 代码分发 | 推到 GitHub，Mac mini `git clone` / `git pull` 同步 |
| 调度方式 | **不需要常驻进程**；用 macOS 原生 `launchd` 定时任务（一次性脚本，跑完即退） |
| 运行时机 | 每天**北京时间 08:00**（美股收盘后次日早晨，数据已全量更新，最稳） |
| Python 环境 | 标准 `venv` + `pip`（Mac mini 上重建，不复用开发机的 `.venv`） |
| 模型文件 | 进 git（`models/*.ubj` + `*.json`，约 140KB） |
| 历史数据 | `data/*.csv` 提交进 git 一起带到 Mac mini（特征需全序列计算，需历史打底） |
| 通知渠道 | Telegram Bot（`curl` 调 sendMessage） |
| 电源状态 | Mac mini 基本 24 小时常开（可能自动睡眠） |
| 网络 | Mac mini 有干净国际网络，**无需代理**（与开发机不同） |

## 本轮交付范围

本轮**仅沉淀方案文档**（task.md + plan.md），不写代码、不部署。待方案确认无误后再进入实施。

## 当前已具备（前序工作产出）

- `ml/train_export.py`：全量训练并导出模型 + 元数据（已完成、本地验证通过）
- `ml/predict.py`：加载模型对最新交易日推理，输出概率 + is_signal_day + feature importance + 数据新鲜度（已完成、本地验证通过）
- `models/spy_nday5_v3.ubj` + `.json`：已导出，样本外 AUC-ROC≈0.66
- 信息泄漏审计：features_v3 全部 21 个特征无未来泄漏，实时推理成立

## 尚缺（本方案要规划的实施项）

1. `run_daily.sh`：每日流程包装脚本（拉数据 → 推理 → 报告 → 推送）
2. Markdown 报告生成器
3. Telegram 推送函数
4. `launchd` 配置（`.plist`）+ Mac mini 部署步骤
