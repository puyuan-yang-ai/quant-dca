# 交接文档：MMA Forecast 2026 年报预测提取（金融 + 占星双文件）

## 项目背景

- **项目**：`/home/puyuyang/project/study/quant-dca`（SPY/SMH 多层次定投回测系统）
- **分支**：master | 最新 commit：`e35632a 0511`
- **本次任务定位**：`docs/tasks/raymond-merriman-forecast-2026-annual-almanac/` 下的 MMA 占星金融年报预测提取
- **用户身份**：摆动交易者（~2 周持仓周期），主力交易美股大盘指数；正在评估能否把 MMA 占星因子加入现有 ML 模型（已有 NDay5/RSI/Breadth/VIX 等特征）
- **MMA 体系研究脉络**（已有产出）：
  - `samples/` 三份样本 PDF（日报/周报/月报）+ 文本提取
  - `weekly-report-verification.md` (1048 行，得分 7.7/10)
  - `monthly-report-verification.md` (1083 行，得分 6.2/10)
  - `forecast_2026.md`（年报 OCR markdown，2503 行，末段 OCR 乱码）

## 已完成的工作

本次会话产出**两个新文件**，均位于 `/home/puyuyang/project/study/quant-dca/docs/tasks/raymond-merriman-forecast-2026-annual-almanac/`：

### 1. `forecast_2026_market_predictions.md`（873 行）— 金融市场预测

- **第一部分速览表**：A 类（价位+时间双锁定）28 条 + B 类（时间+方向）18 条
- **第二部分 CRD 总表**：~50 个独立反转日窗口，按月合并 + 按标的拆分 + 季度版本
- **第三部分**：12 个标的详细预测（DJIA / NASDAQ / Gold / Silver / T-Notes / DXY / USD-JPY / EUR / CHF / Bitcoin / Crude Oil / Corn-Wheat-Soybeans）
- **第四部分**：4 季时间窗口预测

### 2. `forecast_2026_astrological_factors.md`（714 行）— 占星因子库

- **第一部分**：18 个 Level 1 + 25+ Level 2-3 占星事件结构化总表 + 22 个 ML 因子设计建议
- **第二部分**：长周期占星背景（New Aira / Aries Vortex / Saturn-Neptune 历史先例 1882/1917/1952/1989 / Lunar Nodal 衰退周期）
- **第三部分**：3 次水星逆行 + 1 次金星逆行（含 1962-2018 历史先例对比）
- **第四部分**：2 次日食 + 2 次月食（含 8/12 日食对全球领导人本命星图激活分析）
- **第五部分**：4 季入境图（Washington D.C.）详细分析
- **第六部分**：12 位领导人/国家预测（Trump/Putin/Xi/BOJ/Fed/Macron/MBS/Ishiba/von der Leyen/America250）
- **第七部分**：行星-行业-标的占星映射

### 关键执行细节

- **OCR 乱码处理**：年报 forecast_2026.md 第 1900-2503 行是 OCR 失败的星历表（行星位置数字表），已确认无可提取内容并跳过
- **价位双区间字段**：保留宽/窄两个字段（例 DJIA 18 年顶 49,400-57,750 + 重点 51,609-52,342），便于 ML 分级评分
- **跨文件交叉引用**：每条市场预测在"占星支撑"列指向占星文件中的事件 ID
- **验证状态约定**：⏳待验证 / ✅命中 / 🟡部分命中 / ❌未命中 / ⚪不可验证

## 待完成的工作

按优先级排列：

### 1. 年报预测的滚动验证（高优先级）
随时间推移，A 类的 28 条预测需要逐条验证。**最先到期的两条**：
- **A-007 Gold 31 月底**：理想 2025-12 末，可能延至 2026-01-02 月，目标 $2,680-3,336（偏多 $3,300-3,600）
- **A-009 Silver 26 月底**：2025-07 至 2026-05（土海合相 ±3 月内），目标 $37.64±$3.97
- **A-014 USD 长期底**：2026-01 至 06，目标 $86-87

可以现在用 yfinance 拉数据初步对账（土海合相 2026-02-20 是关键节点，已经过去了）

### 2. 用户提出的两个观察需要后续讨论
- **S&P 500 缺失问题**：年报只覆盖 DJIA + NASDAQ，无 SPX/ES。用户主交易标的可能涉及 SPX → 需评估"用 DJIA 周期推 SPX"的精度损失
- **颗粒度问题**：年报最细只到 CRD（3-5 天窗口），无日级买卖点 → 用户可能需要订阅周报/月报（$XXX/月）才能用于日内交易

### 3. ML 因子提取实验（中优先级）
占星文件第一部分已设计 22 个 ML 因子。下一步可以：
- 用 `pip install pyswisseph` 实现因子计算
- 在 `quant-dca` 现有 ML 流程（NDay5/RSI/Breadth/VIX 特征旁）加占星因子
- 跑一次对比实验：纯技术因子 vs 技术+占星因子的 Sharpe/Calmar

### 4. 待提取的内容（低优先级，年报内容已基本覆盖）
- 年报 page 80-92 美国国家章节中"国家本命星图分析"细节（已抓取核心，未深挖）
- BRICS/中国/印度/俄罗斯本命盘细节（年报未深入，但 MMA 月报会涉及）

## 关键决策

### 决策 1：拆成两个文件（金融 + 占星）
**原因**：用户明确要求；分开后金融文件可直接做对账，占星文件可做 ML 因子源 + 地缘事件归档；通过 ID 交叉引用避免重复

**否决方案**：单一文件——会过长（1500+ 行），grep 困难，ML 解析时还要二次过滤

### 决策 2：保留双区间字段（宽/窄）
**原因**：原文经常给"宽范围"+"特别关注的窄范围"（如 DJIA 18 年顶宽 49,400-57,750 / 窄 51,609-52,342）。验证时可分级评分：命中窄=满分，仅命中宽=部分得分

### 决策 3：包含 Type E 地缘领导人预测
**原因**：用户明确要求纳入。这部分对验证占星派系整体准确率有价值（独立第六章便于交叉验证）

### 决策 4：使用 ⏳/✅/🟡/❌/⚪ 验证状态标注
**原因**：与之前 weekly/monthly verification 文档风格一致，便于后续逐条追踪

### 决策 5：ML 因子设计放在占星文件第一部分
**原因**：22 个字段是可直接编码的因子设计，紧跟事件总表方便参考。配套推荐 Swiss Ephemeris + pyswisseph

## 注意事项

### 踩过的坑

1. **年报末段 OCR 乱码**：1900-2503 行是行星位置星历表，OCR 完全失败。**不要试图从那部分提取数据**——所有有用的日期信息已在前面"季节预测"章节包含
2. **WebFetch API 之前报错**：曾出现 "Deployment of claude-haiku-4-5-20251001 not found"，避免直接用 WebFetch 抓 MMA 网站，改用 curl + Bash
3. **PDF 读取限制**：本地无 pdftoppm，必须用 `pdfminer.six` 库（已安装）；超大输出会触发 token 限制，用持久化文件中转
4. **价位历史误读案例**：用户曾把 ES 2026-03-31 (低 6,353) 和 2025-03-31 (低 5,533，落入 MMA 周报支撑 5,505-5,537) 混淆。**所有日期对账需明确年份**
5. **Saturn-Neptune 合相日期**：精确日 2026-02-20，但作者扩展为 ±8-11 个月窗口（2025-06 到 2026-10），所有相关预测都在这个大窗口里
6. **MMA 体系产品分层**：年报（macro）→ 月报 ($165/月，周期分析）→ 周报 ($75/月，CRD+建议）→ 日报 ($595/月，日内）。颗粒度逐级精细

### 容易忽略的步骤

- 用 ephem/skyfield 计算行星位置时，注意**地心黄经**（geocentric longitude）vs 日心；MMA 用的是地心
- 北交点（North Node）是 18.6 年逆向运行，方向与其他行星相反
- 入境图（Ingress Chart）必须用**目标地点**（华盛顿 DC）的当地时间换算 GMT
- "Aries Vortex" 不是单一相位，是 4 外行星集合排列，无单一精确日期；用 2025-2027 的窗口处理

## 相关引用

### 本次产出（核心）
- `/home/puyuyang/project/study/quant-dca/docs/tasks/raymond-merriman-forecast-2026-annual-almanac/forecast_2026_market_predictions.md`
- `/home/puyuyang/project/study/quant-dca/docs/tasks/raymond-merriman-forecast-2026-annual-almanac/forecast_2026_astrological_factors.md`

### 数据源
- `/home/puyuyang/project/study/quant-dca/docs/tasks/raymond-merriman-forecast-2026-annual-almanac/forecast_2026.md`（原始 OCR 文档，2503 行）

### 同系列已有验证文档（可参考风格）
- `/home/puyuyang/project/study/quant-dca/docs/tasks/260510-xxx/weekly-report-verification.md`
- `/home/puyuyang/project/study/quant-dca/docs/tasks/260510-xxx/monthly-report-verification.md`
- `/home/puyuyang/project/study/quant-dca/docs/tasks/260510-xxx/samples/`（三份样本 PDF）

### 现有 ML 特征参考
- 项目 README / CLAUDE.md：详细说明 ComposableStrategy 系统，10+ Entry 模块（NDay/RSI/Breadth/VIX/SafeHaven 等）
- `src/modules/entry.py`：现有信号入口，新加占星因子可在此扩展
- `src/breadth_divergence.py`、`src/rsi_signals.py`：现有信号模块的实现模板

### 外部资源（占星 ML 必备）
- Swiss Ephemeris: https://www.astro.com/swisseph/
- Python 库：`pyswisseph`（推荐）、`ephem`、`skyfield`
- MMA 官网：https://www.mmacycles.com/

## 建议使用的技能

### 下一会话必用
- **`superpowers:brainstorming`**：在动手编码占星 ML 因子前，先完整 brainstorm 因子选择策略（避免一次性引入 22 个特征导致过拟合）
- **`superpowers:systematic-debugging`**：年报对账过程中如出现"日期对不上"问题（参考之前 ES 期货年份混淆案例），系统化排查

### 实施 ML 实验时
- **`superpowers:writing-plans`**：占星因子加入 ML 是多步任务（数据计算/特征对齐/回测/对比），先写实施计划
- **`superpowers:test-driven-development`**：因子计算函数（如"距最近 Level 1 相位天数"）必须写单测，验证与 Swiss Ephemeris 标准星历对得上
- **`superpowers:verification-before-completion`**：完成因子集成后用具体数据点验证（如 2026-02-20 那天 `is_within_orb_saturn_neptune_conjunction = True`）

### 验证年报预测时
- **`Explore` agent**：抓取实时市场数据（yfinance）批量对账可用，避免污染主上下文
- **`general-purpose` agent**：长时间历史数据回算（如计算所有 2025 CRD 命中率）适合后台跑

---

**摘要**：完成 MMA Forecast 2026 年报双文件提取（金融预测 873 行 + 占星因子 714 行 = 161 条独立预测）；下一步可滚动验证或集成 ML 因子。