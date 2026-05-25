---
description: 基于最新剧本状态，生成 SPY Spread 期权订单参数（老虎证券组合单）；内置 DTE 铁律、70% 止盈纪律、半凯利仓位计算
argument-hint: <scenario_evolution.md 绝对路径，支持 @workspace/...>
---

## 参数校验（最高优先级，必须先执行）

`$ARGUMENTS` 应为 `YYYYMMDD_scenario_evolution.md` 文件的绝对路径。若以 `@workspace/` 开头，先把它替换为 `/home/puyuyang/workspace/`；规范化后仍非 `/` 开头则停止执行，回复：

如果 `$ARGUMENTS` 为空或未提供，请立即停止执行，并仅回复以下提示，不要执行任何后续步骤：

> ⚠️ 缺少必需参数：请提供 `<scenario_evolution.md 的绝对路径>` 后重新触发。

## 任务

请读取 `$ARGUMENTS` 指向的剧本推演文件，以该文件中**最新的剧本状态**（最后一次 ✅ / ⚠️ / ❌ 校验结果）作为唯一判断依据，生成可在老虎证券（Tiger Brokers）直接执行的 SPY 期权组合单订单参数。

### 工作流（两阶段）

**Phase 1 — 草稿策略**：读取剧本文件，根据方向判断、DTE 铁律、Strike 选择规则，确定策略结构（类型、到期日、行权价）。此阶段权利金为估算值。

**Phase 2 — 权利金验证**：策略结构确定后，运行以下命令获取真实 bid/ask：

```bash
# 示例：Bull Call Spread，买 745C / 卖 760C，同到期 2026-06-12
python scripts/fetch_spy_options.py \
  --legs "call,2026-06-12,745" "call,2026-06-12,760"
```

用脚本输出的 **Mid Price** 回填订单模板的"参考权利金"字段，重新计算：
- 组合净权利金（净 debit 或净 credit）
- 最大盈利 / 最大亏损
- 70%、80% 止盈触发价

⚠️ 如果脚本报错（到期日不存在 / Strike 不在链上），根据错误提示调整到最近可用的到期日或 Strike，重新运行，不允许保留估算占位符 `$X.XX` 落盘。

完成后，请将订单参数落盘为以下 Markdown 文件，**放置在与 `$ARGUMENTS` 同一目录下**，文件名使用系统当前时刻命名：

- `YYYYMMDD_HHMM_orders.md`：YYYYMMDD 为今日日期，HHMM 为触发时刻（24 小时制）。每次触发都生成独立新文件，不覆盖历史。

### 要求

- 标的：SPY（SPDR S&P 500 ETF）
- 策略：两腿 Spread 期权组合单，由 AI 根据当前剧本方向判断选择合适的 Spread 类型：
  - 看多：Bull Call Spread 或 Bull Put Spread
  - 看空：Bear Put Spread 或 Bear Call Spread
- 不做四腿及以上的复杂结构
- 若当前主剧本状态为 ❌ 已失效，请明确说明，不生成订单参数，等待新的剧本判断（此时不落盘订单文件）

#### IV 环境与 Vertical 类型匹配（2 档规则）

同向看多/看空时，须根据当前 VIX 水平选择更优的 Vertical 类型：

| 方向 | VIX 环境 | 优先选择 | 理由 |
|------|---------|---------|------|
| 看多 | VIX ≥ 22（高 IV） | **Bull Put Spread（Credit）** | 卖出高价 vol，等 IV 回落 + 方向双重获利 |
| 看多 | VIX < 22（中低 IV） | **Bull Call Spread（Debit）** | 期权便宜，买 vol 方向最大化 |
| 看空 | VIX ≥ 22（高 IV） | **Bear Call Spread（Credit）** | 对称逻辑，卖高 IV 看空 |
| 看空 | VIX < 22（中低 IV） | **Bear Put Spread（Debit）** | 标准方向性工具 |

**VIX 获取方式**：运行 `fetch_es_for_mma.py` 时脚本已输出当日 VIX 收盘值（见脚本 §2.4 输出格式）。

#### 主剧本单一聚焦

主战场层订单**只针对主剧本（当前概率最高的剧本）生成**，备选剧本不单独开仓，仅作为止损规则中的"剧本切换触发条件"。

**原因**：多剧本同时开仓会导致：
1. 仓位冲突（如 A 看多 + C 看跌同时持仓 = 跟自己对赌）
2. 资金分散（$2,700 切成 4 份后半凯利优势丧失）
3. 心态混乱（多笔仓位无法专注 70% 止盈纪律）

主剧本对应的订单中，止损条件必须显式包含一条：
> 若 `mma-3-verify` 把备选剧本（B/C/D）从 ⚠️ 升级为 ✅ 且概率超越当前主剧本 → 立即全平本订单

#### 拒绝开仓条件（强制）

满足以下任一条件，AI 必须输出"等待剧本明朗，本次不开仓"，**不落盘订单文件**：

1. ❌ 主剧本当前概率 < 60%（信号强度不足）
2. ❌ 前两高剧本方向相反 且 概率差 < 20%（如 A=45% 看多，B=40% 看空）
3. ❌ 主剧本被标记为 ❌ 已失效（已有规则，此处重申）

输出格式：
> ⚠️ **本次不开仓**：主剧本概率 XX% 未达 60% 阈值 / 前两高剧本方向冲突且概率接近，等待 mma-3-verify 后续校验明朗后再触发。

---
### 下单铁律（必须遵守，违反则方案作废）
#### 铁律 1：DTE 匹配公式
> **DTE = thesis 关键日距今交易日数 + 5-7 天缓冲（绝对不超过 +10 天）**
- **thesis 关键日**：剧本预测的顶部/底部时间（看涨取 Crest 日；看跌取 Trough 日）
- **距今交易日数**：今天到关键日之间的实际交易日数（跳过周末、节假日）
- **缓冲 5-7 天**：留出 thesis 微小偏移的容忍空间
**正面示例**：
- 今日 5/22，thesis Crest 6/6（10 个交易日后）→ DTE 选 **6/12（15 DTE）** ✅
- 今日 5/22,thesis Trough 5/28（4 个交易日后）→ DTE 选 **6/2（8 DTE）** ✅
**反面示例**（实战已踩坑）：
- 今日 5/19，thesis Crest 6/6（13 个交易日后），却选 **6/19（22 DTE）** ❌
  → 价格触及短腿时仍有 14 天 DTE 未消耗，**spread 只能拿到 max profit 的 30-50%**
**核心原理**：Vertical Spread 在到期日才能拿到 max profit。DTE 越长，"价格到达短腿"和"到期日"之间的时间差越大，短腿外在价值无法收割，**导致只赚少量利润（30% 而不是 80%）**。
---
#### 铁律 2：70-80% 止盈纪律
> **达到 max profit 的 70-80% 立即全平，禁止贪到 100%。**
- **平仓触发价 = 入场 debit + 0.70 × max profit**（保守版）
- **平仓触发价 = 入场 debit + 0.80 × max profit**（积极版）
- **例**：入场 debit $3，max profit $7 → 组合现值达到 **$7.9-8.6** 立即全平


#### 铁律 3：Strike 选择规则

> **长腿管"我从哪里出发"（看当前价）；短腿管"我到哪里收手"（看目标/关键位）。**

| Spread 类型 | 长腿（buy）Strike | 短腿（sell）Strike |
|---|---|---|
| **Bull Call Spread**（Debit）| **ATM 或轻微 OTM**（当前价 +1~3 美元）| **thesis 价格目标 / 阻力位** |
| **Bear Put Spread**（Debit）| **ATM 或轻微 OTM**（当前价 -1~3 美元）| **thesis 价格目标 / 支撑位** |
| **Bull Put Spread**（Credit）| **短腿下方 5-10 美元**（保护腿，限定亏损宽度）| **关键支撑位**（如 TIP / Weekly Support）|
| **Bear Call Spread**（Credit）| **短腿上方 5-10 美元**（保护腿，限定亏损宽度）| **关键阻力位**（如 Weekly Resistance）|

##### 核心原理

- **Debit Spread**（买差价、付钱）：**长腿决定 delta 和入场成本**，短腿决定盈利上限
- **Credit Spread**（卖差价、收钱）：**短腿决定 credit 厚度和盈利点位**，长腿只是限定最大亏损的保护腿

##### 反面教材（实战易犯错）

- ❌ Bull Call Spread 长腿放在 thesis 目标（如 760）→ 几乎没收益空间，纯亏 debit
- ❌ Bull Call Spread 长腿放在深 ITM（如 720，当前 743）→ delta 接近 1，杠杆消失，付了大头还赚不多
- ❌ Bull Put Spread 短腿放在远离支撑的安全区（如 700，TIP 在 730）→ credit 太薄，丢掉"卖在关键位"的全部优势
- ❌ Vertical Spread 两腿都"靠近当前价"（如 Bull Call 745/750）→ spread 宽度太窄，max profit 太小

##### 收益密度公式

- 单张 max profit = (短腿 strike − 长腿 strike) − net debit
- 单张 ROI = max profit ÷ net debit
- **追求高 ROI 时**：长腿尽量轻微 OTM（降 debit）+ 短腿正好在目标位（拉大 spread 宽度）

---

### 输出格式

请严格按照以下参数清单格式输出，每个策略方案独立一块：

---

**策略名称**：（如 Bull Call Spread）
**方向判断**：做多 / 做空
**当前依据**：（一句话说明当前触发此策略的核心逻辑）
**DTE 推导**：（必填）thesis 关键日 YYYY-MM-DD 距今 X 个交易日 + 缓冲 Y 天 = 选 YYYY-MM-DD 到期（DTE = Z）

| 参数 | 买入腿 | 卖出腿 |
|------|--------|--------|
| 标的 | SPY | SPY |
| 方向 | Buy | Sell |
| 期权类型 | Call / Put | Call / Put |
| 到期日 | YYYY-MM-DD | YYYY-MM-DD |
| 行权价 | $XXX | $XXX |
| 合约数量 | X 张 | X 张 |
| 参考权利金 | $X.XX | $X.XX |
| 组合净权利金 | 净支出 / 净收入 $X.XX | |
| 建议限价 | $X.XX（组合单总价） | |

**最大亏损**：$XXX（每组）
**最大盈利**：$XXX（每组）
**盈亏比**：X : 1
**建议仓位（半凯利）**：
- 主剧本概率 p = X%，盈亏比 b = max_profit / max_loss = $X / $X = X.XX
- 原始凯利：f* = (p × b − (1−p)) / b = XX.X%
- 半凯利：f* / 2 = **XX.X%** 的期权预算
- 建议下注：期权预算 $1,890 × XX.X% = **$XXX（约 X 组，每组 debit $X.XX × 100）**
- 占总资金约 X.X%
- ⚠️ [若 f_adjusted < 5%]：半凯利 < 5%，期望优势偏弱，建议拉大 spread 宽度或等待更高概率确认
- ⚠️ [若 f_adjusted > 30%]：已压至硬性上限 30%，单笔期权仓位不超过此值

仓位计算铁律：
- Step 1：从 scenario_evolution.md 读取主剧本当前概率 p
- Step 2：计算 b = max_profit ÷ max_loss（Phase 2 拿到真实权利金后计算）
- Step 3：原始凯利 f* = (p × b − (1−p)) ÷ b
- Step 4：半凯利 f_adjusted = f* ÷ 2
- Step 5：f_adjusted < 0.05 → 警告"期望优势不足"；f_adjusted > 0.30 → 强制压至 0.30
- Step 6：建议张数 = floor(期权预算 × f_adjusted ÷ (净debit × 100))，向下取整

**盈亏平衡点 (Breakeven)**：SPY = $XXX（到期日股价等于此值时盈亏为 0）
- Debit Spread Breakeven = 长腿 Strike + 净 Debit
- Credit Spread Breakeven = 短腿 Strike - 净 Credit（看多）/ + 净 Credit（看空）

**保证金占用**（仅 Credit Spread 需要，Debit Spread 填 N/A）：
$XXX = (Strike 差 × 100 - Credit × 100) × 张数

**止损条件**：（具体触发条件，如 SPY 跌破 $XXX 或组合亏损超过 X%；或主剧本 ❌ 化立即全平；或备选剧本概率超越主剧本 → 立即全平）
**止盈条件**（三层硬性触发，按先到者执行）：
- 价格止盈：spread mark ≥ **$X.XX**（= debit $X.XX + 70% × max profit $X.XX）→ 立即全平
- 时间止盈：thesis 关键日 YYYY-MM-DD 收盘前 30 分钟 → 无论盈亏全平
- 超预期止盈：提前 ≥ 3 个交易日且 ROI ≥ +80% → 立即全平

**决策推理链**（每个方案必填）：
1. **类型选定理由**：当前 VIX = XX.X，对应 [高 / 中低] IV → 优先选 [Credit / Debit] → 选定 XXX Spread
2. **DTE 选定理由**：thesis 关键日 YYYY-MM-DD 距今 X 个交易日 → +5-7 天缓冲 → 选 YYYY-MM-DD（如有节假日跳过说明）
3. **长腿 Strike 理由**：当前 SPY $XXX → 按 Strike 规则取 [ATM / ATM+2 / 支撑下 5-10] → 选 $XXX
4. **短腿 Strike 理由**：thesis 目标位 / 关键支撑阻力位 $XXX → 选 $XXX
5. **仓位计算**：半凯利 = XX.X% → 占期权预算 $1,890 → 单笔 $XXX → X 张
6. **被淘汰的备选**：（如有，说明排除理由，例如"曾考虑 6/19 到期但 DTE 超过 +10 天上限被否"）

---

### 附加说明

- 到期日的选择：**禁止默认 3-4 周 DTE**（教科书法则不适用于有明确时间窗的 thesis）；每个方案必须按铁律 1 公式显式列出 DTE 推导过程
- 行权价的选择需结合当前关键支撑位和阻力位
- 如有多个策略方案，按"概率 × 盈亏比"排序，优先展示最推荐的方案
- 落盘文件路径必须与 `$ARGUMENTS` 在同一目录
- 每个方案必须显式列出"70% 止盈触发价计算"（debit + 0.70 × max profit = $X.XX），便于人工审计
- **Greeks（Delta / Theta / Vega / Gamma）的使用边界**：
  - ✅ **允许**：`fetch_spy_options.py` 输出的 Delta / IV 可作为"事后核对参考"，用于发现 strike 选择是否极端偏差（如长腿 delta < 0.20 或 > 0.85 提示 strike 异常）
  - ❌ **禁止**：以"Greeks 不在教科书甜点区间"为理由否决任何已通过 DTE 铁律 + Strike 规则 + 半凯利三重审核的方案
  - **原因**：你是方向性交易者，Greeks 教科书优化针对做市商设计，会与本系统核心铁律冲突

---

### 后续可选升级

💡 基础 Vertical Spread 已覆盖 70-80% MMA 场景。如本次市场结构特别适合高级工具（时间窗精确、想保留上涨敞口、有强支撑可叠加 Credit 补贴等），可使用 `/mma-5-upgrade` 命令，传入本命令生成的 `YYYYMMDD_HHMM_orders.md` 文件路径，对该订单进行 Round 2 升级评估（Long Call + BPS / Diagonal / Short DTE Long Call）。不需要升级时跳过即可。
