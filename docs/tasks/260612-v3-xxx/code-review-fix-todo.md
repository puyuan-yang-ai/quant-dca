# Code Review Fix TODO

本文档整理本轮代码审查后建议修改的所有点。目标是先修正会影响 ML 结论可信度或脚本可运行性的内容，再处理依赖、清理和绘图脚本一致性问题。

## P0 - Correctness

- [x] 对齐 ML 的 `NDay5` 信号语义与真实回测语义。
  - 当前风险：`ml/labeling.py::generate_nday_signals()` 使用当天 `close < EMA` 计数，但 `BacktestEngine` 的入场上下文使用 `prev_close < ema_val` 更新连续计数。
  - 影响范围：`ml/run_mvp.py`、`scripts/show_chart.py --ml`、`ml/features_v1.py`、`ml/features_v2.py`、`ml/features_v3.py`。
  - 建议做法：抽出一个共享的 NDay 信号/连续计数 helper，或者在 `generate_nday_signals()` 中显式复刻 `BacktestEngine` 语义。
  - 验收结果：同一份 SPY 数据上，ML NDay5 日期集合与回测语义一致，差集为 0。

- [x] 清理 `safe_haven` 的隐性运行时依赖。
  - 当前风险：`features_v1.py`、`features_v2.py`、`features_v3.py` 的 `_compute_entry_signals()` 仍然调用 `_load_safe_haven()` 并生成 `sig_safe_haven`，但该列不在最终 `feature_cols` 中。
  - 影响：即使模型不用这个特征，只要 `data/safe_haven.csv` 缺失、格式变化或日期不对齐，特征构建仍可能失败。
  - 建议做法：从 `_compute_entry_signals()` 删除 `_load_safe_haven()`、`sig_safe_haven` 计算和返回列；如果未来要恢复该特征，再把它作为显式候选特征加回。
  - 验收结果：`features_v1.py`、`features_v2.py`、`features_v3.py` 不再读取 `safe_haven.csv`；当前激活版本 `python -m ml.run_mvp` 跑通。

## P1 - Runtime Failures

- [x] 修复两个旧的 `ml.features` 导入。
  - 当前风险：`ml/show_signals_chart.py` 和 `ml/compare_entry_signals.py` 引用不存在的 `ml.features`，运行会直接 `ModuleNotFoundError`。
  - 建议做法：改为与 `ml/run_mvp.py` 一致，使用 `ml.versions.get_active_config()` 和 `importlib.import_module(config["features_module"])` 加载当前激活特征模块。
  - 验收结果：`python -m ml.show_signals_chart --help` 和 `python -m ml.compare_entry_signals` 均通过。

- [x] 补齐 ML 依赖声明。
  - 当前风险：代码已使用 `xgboost`、`sklearn`、`scipy`、`numpy`，但 `requirements.txt` 未声明这些依赖。
  - 建议做法：在 `requirements.txt` 增加 `xgboost`、`scikit-learn`、`scipy`、`numpy`。
  - 验收结果：`requirements.txt` 已增加 ML 依赖；当前环境中 `python -m ml.run_mvp` 跑通。

## P2 - Integration Cleanup

- [x] 清理 `scripts/show_chart.py` 未使用的 swing low 旧逻辑导入。
  - 当前风险：脚本已改为展示 `SL7`，但仍导入 `detect_swing_highs` 和 `filter_swing_lows_by_drop`。
  - 建议做法：删除未使用 import，保持入口代码和图表含义一致。
  - 验收结果：`python -m py_compile scripts/show_chart.py` 通过；`python -u scripts/show_chart.py --env ml-test --ml --port 9876` 完成回测、生成 ML 标记并启动图表服务。

- [x] 明确 `scripts/plot_mma_scenario.py` 的 `--scenario` 行为。
  - 当前风险：脚本要求传 `--scenario`，但只使用该路径的父目录作为输出位置，图表内容仍来自硬编码的 `DATA START` 区块。
  - 建议做法：二选一：
    - 保持模板填充工作流，但增加校验：`scenario` 文件存在，文件标题日期与 `REPORT_DATE` 一致，否则报错。
    - 或将脚本改造成真正解析 `scenario_evolution.md` 的入口。
  - 验收结果：合法 `20260608_scenario_evolution.md` 可生成图；传入 `20260601_scenario_evolution.md` 会明确报 metadata mismatch。

- [x] 同步 `.cursor/commands/plot_mma_scenario_template.py` 与生成脚本的校验逻辑。
  - 当前风险：模板和生成脚本共享同一段固定绘图逻辑，如果只改其中一个，后续命令生成的新脚本会覆盖修复。
  - 建议做法：先改模板，再从模板重新生成 `scripts/plot_mma_scenario.py`，确保 `DATA END` 以下逻辑一致。
  - 验收结果：模板和生成脚本均已加入同一套 scenario metadata 校验逻辑。

## Suggested Execution Order

1. 先修 `NDay5` 语义对齐，并重新跑 `python -m ml.run_mvp` 记录新指标。
2. 清理 `safe_haven` 隐性依赖，再跑一次 `python -m ml.run_mvp` 确认指标变化只来自 P0 修复。
3. 修复两个旧入口导入，并分别运行 `ml.show_signals_chart` 与 `ml.compare_entry_signals`。
4. 更新 `requirements.txt`。
5. 做 `show_chart.py` import 清理。
6. 最后处理 MMA scenario plotting 的校验和模板同步。

## Verification Checklist

- [x] `python -m py_compile experiments/configs.py scripts/show_chart.py src/interactive_chart.py ml/*.py`
- [x] `python -m ml.run_mvp`
- [x] `python -m ml.compare_entry_signals`
- [x] `python -m ml.show_signals_chart --help`
- [x] `timeout 45s python -u scripts/show_chart.py --env ml-test --ml --port 9876`
- [x] `python scripts/plot_mma_scenario.py --scenario <valid scenario_evolution.md>`
- [x] 用错误或不匹配日期的 scenario 文件验证绘图脚本会明确报错。
