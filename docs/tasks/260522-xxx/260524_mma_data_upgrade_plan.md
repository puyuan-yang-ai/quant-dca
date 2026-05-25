# MMA 数据源升级实施方案（精简版 v2）
_起草：2026-05-24 / 精简：2026-05-24_

---

## 一、背景与目标

| 现状问题 | 升级目标 |
|---------|---------|
| 数据源依赖 Tiingo API Key，环境限制多 | 改用 yfinance，零配置，已在 requirements.txt |
| SPY × 10.06 系数换算 ES，存在基差误差 | 直接拉 `ES=F`，已验证与 ESM26 一致 |
| 期权权利金全是 AI 估算占位符 `$X.XX` | 生成草稿策略后调脚本拉真实 bid/ask 回填 |
| 每次调提示词 AI 都临时生成取数代码 | 固化为独立脚本，提示词只写调用命令 |
| 同向看多时 Bull Call vs Bull Put 靠感觉选 | 加入 IV 环境匹配规则（2 档），根据 VIX 自动选更优类型 |
| 建议仓位是拍脑袋的"X 组" | 引入**半凯利公式**，基于概率和盈亏比计算理论仓位 |
| 淘汰逻辑不可见 | 每个方案强制输出**决策推理链**（6 条） |
| 输出字段不全，Tiger 下单页核对困难 | 补齐 Breakeven、保证金占用 2 个字段 |
| Greeks 教科书优化可能否决合理交易 | 明确"Greeks 仅作事后核对参考，不允许否决方案" |
| 多剧本时仓位混乱（每剧本都开 = 自己对赌）| 主战场只针对主剧本；双高概率反向剧本时强制不开仓 |
| Vertical 之外的高级工具栈被硬性排除 | 独立 `/mma-6-advanced` slash command 承载，不进 mma-5 默认流程 |

**改动范围：新增 2 个脚本 + 修改 3 个提示词文件 + 新建 1 个提示词文件 + 清理 1 处重复内容**

**账户参数（写入提示词作为默认值）**：
- **总仓位**：$18,000
- **期权专用预算**：$2,700（15% 总资金）
  - 主战场层：$1,890（70%，mma-5 默认调用）
  - 机会层：$540（20%，突破/回踩加仓，暂不实施）
  - 现金缓冲：$270（10%，常驻不动）
- **单笔上限**：$810（期权预算的 30%，即使半凯利算出更高也压顶）
- **风控熔断**：月内亏损 ≥ $810 → 暂停新仓 1 周；连续 3 笔失败 → 期权预算临时砍半至 $1,350

---

## 二、新增脚本 1：`scripts/fetch_es_for_mma.py`

### 2.1 用途
替代 `fetch_spy_for_mma.py`，用 yfinance 直接拉 ES 期货日线数据，增量维护 `data/es_daily.csv`，输出 OHLC 供 `mma-1-analyze` 和 `mma-3-verify` 消费。

### 2.2 命令行接口

```bash
# 基本用法（取最近 7 个交易日，供 mma-3-verify 调用）
python scripts/fetch_es_for_mma.py --days 7

# 第一次运行 / 手动补数（默认回填 60 天）
python scripts/fetch_es_for_mma.py --days 60

# 供 mma-1-analyze 调用（对比周报日期）
python scripts/fetch_es_for_mma.py --days 10
```

### 2.3 CSV 维护逻辑

- 文件路径：`data/es_daily.csv`
- 列：`date, open, high, low, close, volume`
- **增量逻辑**：
  1. 如果 CSV 不存在 → 拉最近 60 天历史，全量写入
  2. 如果 CSV 已存在 → 读取末尾日期，只拉"末尾日期之后"的新数据，追加行，不重写旧数据
  3. 同日数据不重复写（以 `date` 去重）

### 2.4 标准输出格式（供提示词中 AI 读取）

```
# ES 期货行情（MMA 校验数据）

- 数据源：yfinance ES=F（S&P 500 E-mini 连续合约）
- 已验证：ES=F 与 ESM26 一致，无需系数换算
- 本地缓存：data/es_daily.csv（增量更新）
- 拉取窗口：YYYY-MM-DD → YYYY-MM-DD（N 个交易日）

| 日期 | ES Open | ES High | ES Low | ES Close | Volume |
|------|--------:|--------:|-------:|---------:|-------:|
| ...  | ...     | ...     | ...    | ...      | ...    |

## 最新交易日摘要（YYYY-MM-DD）
- ES 收盘：XXXX.X（日变化 +X.XX%）
- ES 日内振幅：XXXX.X ~ XXXX.X
- **VIX 收盘：XX.XX**（IV 环境参考：≥22 高 IV / <22 中低 IV）
```

> VIX 通过 yfinance `^VIX` 同步拉取，不额外存 CSV，只输出最新收盘值供 AI 判断 IV 环境。

### 2.5 关键实现细节

```python
import yfinance as yf
import pandas as pd
from pathlib import Path

TICKER = "ES=F"
CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "es_daily.csv"

def fetch_incremental(days: int) -> pd.DataFrame:
    """拉取数据，自动决定全量或增量。"""
    if CSV_PATH.exists():
        existing = pd.read_csv(CSV_PATH, parse_dates=["date"])
        last_date = existing["date"].max()
        # 只拉 last_date 之后的数据（多取 5 天缓冲处理节假日）
        start = last_date + pd.Timedelta(days=1)
    else:
        start = pd.Timestamp.today() - pd.Timedelta(days=days * 2)

    df = yf.download(TICKER, start=start.strftime("%Y-%m-%d"), auto_adjust=True)
    # 处理列名、写 CSV...
```

---

## 三、新增脚本 2：`scripts/fetch_spy_options.py`

### 3.1 用途
接收 AI 已确定好的期权合约腿（类型 + 到期日 + 行权价），拉取实时 bid/ask/iv，供 `mma-5-order-pro` 回填真实权利金并重算盈亏比。**不存 CSV，只做实时快照输出。**

### 3.2 命令行接口

```bash
# 单腿查询（调试用）
python scripts/fetch_spy_options.py --legs "call,2026-06-12,745"

# 多腿查询（Bull Call Spread：买 745C + 卖 760C，同到期）
python scripts/fetch_spy_options.py --legs "call,2026-06-12,745" "call,2026-06-12,760"

# 四腿（Diagonal：买 745C 6/19 + 卖 760C 6/6）
python scripts/fetch_spy_options.py \
  --legs "call,2026-06-19,745" "call,2026-06-06,760"

# 每腿格式：type,expiry,strike
# type: call | put
# expiry: YYYY-MM-DD（必须是 SPY 实际存在的到期日，否则报错提示）
# strike: 整数或带 .0 的浮点数
```

### 3.3 标准输出格式

```
# SPY 期权报价（实时快照）
- 查询时间：YYYY-MM-DD HH:MM:SS（市场时区）
- 数据源：yfinance SPY option_chain

## 各腿报价

| 腿 | 类型 | 到期日 | Strike | Bid | Ask | Mid | IV | Delta | OI |
|----|------|--------|--------|-----|-----|-----|----|-------|----|
| L1 | Call | 2026-06-12 | 745 | 3.80 | 3.90 | 3.85 | 0.18 | 0.52 | 12430 |
| L2 | Call | 2026-06-12 | 760 | 1.10 | 1.20 | 1.15 | 0.16 | 0.28 | 8920 |

## 组合计算（按 Mid 价）

| 项目 | 计算 | 结果 |
|------|------|------|
| 净 Debit（付出）| L1 Mid - L2 Mid | $2.70 |
| Max Profit | Strike 差 - 净 Debit | $12.30 |
| Max Loss | 净 Debit | $2.70 |
| ROI（Max）| Max Profit ÷ Net Debit | 455% |
| **70% 止盈触发价** | Debit + 70% × Max Profit | **$11.31** |
| **80% 止盈触发价** | Debit + 80% × Max Profit | **$12.54** |

## 注意事项
- ⚠️ Bid/Ask 使用收盘后快照，下单前请以实盘报价为准
- ⚠️ IV 基于 Mid Price 隐含波动率
```

### 3.4 错误处理

| 场景 | 输出 |
|------|------|
| 指定到期日不存在 | `❌ 2026-06-07 不是 SPY 的有效到期日。最近可用：2026-06-06, 2026-06-12, 2026-06-20` |
| 指定 Strike 不在期权链 | `❌ Strike 747 不在 2026-06-12 的期权链中。最近可用：745, 750` |
| 市场已休市，数据较旧 | `⚠️ 当前为非交易时间，报价为上一交易日收盘快照（YYYY-MM-DD）` |

---

## 四、提示词修改详情

### 4.1 `mma-1-analyze.md` — 第 2 步"核对价格基准"

**删除**旧的 SPY×ratio 换算说明，**替换为**：

```markdown
### 2. 核对价格基准

在项目根目录运行：

```bash
python scripts/fetch_es_for_mma.py --days 10
```

脚本直接输出 ES=F（E-mini S&P 500 连续合约）最近 10 个交易日的真实 OHLC，已验证与 MMA 周报引用的 ESM26 一致，无需系数换算。

将脚本输出的 **ES 点位**与周报中的关键高点、低点、支撑、阻力逐一对照：
- 偏差 < 2 点：正常，直接使用
- 偏差 > 10 点：说明周报使用了不同合约月份，在分析报告中标注实际偏差值

数据同步写入 `data/es_daily.csv`（增量追加，不覆盖历史）。
```

---

### 4.2 `mma-3-verify.md` — 第 1 步"拉取最新市场数据"

**删除**文件顶部"数据口径说明"和旧脚本调用（`fetch_spy_for_mma.py --days 7` + ratio 偏差校准说明），**替换为**：

```markdown
### 1. 拉取最新市场数据

在项目根目录运行：

```bash
python scripts/fetch_es_for_mma.py --days 7
```

脚本输出：
- 最近 7 个交易日的 ES 期货真实 OHLC（ES=F，已验证与 ESM26 一致）
- 最新交易日摘要（收盘、日变化、日内振幅）
- 数据同步追加至 `data/es_daily.csv`

将脚本输出的 ES 点位直接与剧本中的 ESM 关键点位逐一对照，无需系数换算。
```

---

### 4.3 `mma-5-order-pro.md` — 7 处修改

#### 4.3.1 新增两阶段工作流（插入"任务"章节，落盘说明之前）

```markdown
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
```

#### 4.3.2 删除重复的叠加层内容

文件 84-111 行为叠加层评估机制的**散文版**，113-141 行为**表格版**（结构更清晰）。

**操作**：删除 84-111 行（散文版），保留 113-141 行（表格版）。

#### 4.3.3 新增 IV 环境匹配规则（插入"要求"章节末尾）

```markdown
#### IV 环境与 Vertical 类型匹配（2 档规则）

同向看多/看空时，须根据当前 VIX 水平选择更优的 Vertical 类型：

| 方向 | VIX 环境 | 优先选择 | 理由 |
|------|---------|---------|------|
| 看多 | VIX ≥ 22（高 IV） | **Bull Put Spread（Credit）** | 卖出高价 vol，等 IV 回落 + 方向双重获利 |
| 看多 | VIX < 22（中低 IV） | **Bull Call Spread（Debit）** | 期权便宜，买 vol 方向最大化 |
| 看空 | VIX ≥ 22（高 IV） | **Bear Call Spread（Credit）** | 对称逻辑，卖高 IV 看空 |
| 看空 | VIX < 22（中低 IV） | **Bear Put Spread（Debit）** | 标准方向性工具 |

**VIX 获取方式**：运行 `fetch_es_for_mma.py` 时脚本已输出当日 VIX 收盘值（见脚本 §2.4 输出格式）。
```

#### 4.3.4 新增半凯利仓位公式（替换"建议仓位"字段）

将输出格式中的"建议仓位"字段从：

```markdown
**建议仓位**：X 组（占总资金约 X%）
```

替换为：

```markdown
**建议仓位（半凯利）**：
- 主剧本概率 p = X%，盈亏比 b = max_profit / max_loss = $X / $X = X.XX
- 原始凯利：f* = (p × b − (1−p)) / b = XX.X%
- 半凯利：f* / 2 = **XX.X%** 的期权预算
- 建议下注：期权预算 $XXX × XX.X% = **$XXX（约 X 组，每组 debit $X.XX × 100）**
- 占总资金约 X.X%
⚠️ [若 f_adjusted < 5%]：半凯利 < 5%，期望优势偏弱，建议拉大 spread 宽度（提高 b）或等待更高概率确认后再入场
⚠️ [若 f_adjusted > 30%]：已压至硬性上限 30%，单笔期权仓位不超过此值
```

**半凯利公式说明（写入提示词的算法描述）：**

```markdown
仓位计算铁律：

Step 1：从 scenario_evolution.md 读取主剧本当前概率 p（如 0.80）
Step 2：从订单参数计算 b = max_profit ÷ max_loss（Phase 2 拿到真实权利金后计算）
Step 3：原始凯利 f* = (p × b − (1−p)) ÷ b
Step 4：半凯利 f_adjusted = f* ÷ 2
         ÷2 = 半凯利（降低波动率约 50%，牺牲约 25% 期望增长率）
Step 5：硬性边界
         f_adjusted < 0.05 → 输出警告"期望优势不足"，建议不开仓
         f_adjusted > 0.30 → 强制压至 0.30
Step 6：建议张数 = floor(期权预算 × f_adjusted ÷ (净debit × 100))
         向下取整，绝不超凯利上限
```

#### 4.3.5 决策推理链（输出格式新增字段）

在每个候选方案的输出末尾，新增一节 **「决策推理链」**：

```markdown
**决策推理链**（每个方案必填）：
1. **类型选定理由**：当前 VIX = XX.X，对应 [高 / 中低] IV → 优先选 [Credit / Debit] → 选定 XXX Spread
2. **DTE 选定理由**：thesis 关键日 YYYY-MM-DD 距今 X 个交易日 → +5-7 天缓冲 → 选 YYYY-MM-DD（如有节假日跳过说明）
3. **长腿 Strike 理由**：当前 SPY $XXX → 按 Strike 规则取 [ATM / ATM+2 / 支撑下 5-10] → 选 $XXX
4. **短腿 Strike 理由**：thesis 目标位 / 关键支撑阻力位 $XXX → 选 $XXX
5. **仓位计算**：半凯利 = XX.X% → 占期权预算 $XXX → 单笔 $XXX → X 张
6. **被淘汰的备选**：（如有，说明排除理由，例如"曾考虑 6/19 到期但 DTE 超过 +10 天上限被否"）
```

#### 4.3.6 券商核对字段（输出格式补齐 2 个字段）

```markdown
**盈亏平衡点 (Breakeven)**：SPY = $XXX（到期日股价等于此值时盈亏为 0）
- Debit Spread Breakeven = 长腿 Strike + 净 Debit
- Credit Spread Breakeven = 短腿 Strike - 净 Credit（看多）/ + 净 Credit（看空）

**保证金占用**（仅 Credit Spread 需要，Debit Spread 填 N/A）：
$XXX = (Strike 差 × 100 - Credit × 100) × 张数
```

这两个字段是 Tiger 下单页一定会显示的，用于下单后逐字段核对。

#### 4.3.7 Greeks 防御性条款（附加说明新增一行）

```markdown
- **Greeks（Delta / Theta / Vega / Gamma）的使用边界**：
  - ✅ **允许**：`fetch_spy_options.py` 输出的 Delta / IV 可作为"事后核对参考"，用于发现 strike 选择是否极端偏差（如长腿 delta < 0.20 或 > 0.85 提示 strike 异常）
  - ❌ **禁止**：以"Greeks 不在教科书甜点区间"为理由否决任何已通过 DTE 铁律 + Strike 规则 + 半凯利三重审核的方案
  - **原因**：你是方向性交易者，Greeks 教科书优化针对做市商设计，会与本系统核心铁律冲突
```

#### 4.3.8 主剧本单一聚焦 + 拒绝开仓条件（新增到"要求"章节）

```markdown
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
```

---

### 4.4 新建 `.cursor/commands/mma-6-advanced.md`（slash command）

**定位**：Round 2 高级工具升级入口。Round 1（mma-5）默认只输出 Vertical Spread；用户在看完 mma-5 输出后，若想评估更复杂的工具结构，主动触发 `/mma-6-advanced` 进行升级评估。

**承载内容**：

1. **高级工具栈触发清单**（3 种工具 + 适用场景关键词 + 升级理由）
2. **DTE 配比口诀**（Long Call + Bull Put Spread 的 DTE 错配规则）
3. **Diagonal 保证金规则**（老虎证券对 Diagonal 的判断方式 + Early Exercise 风险 + 下单前必查项）
4. **反向 Diagonal 警告**（绝对禁止规则）

**为什么这些不进 mma-5**：
- 70-80% MMA 场景 Vertical 已足够
- 高级工具需要更复杂的退出纪律，管理不当会把利润让回去
- 默认升级会增加 AI 选错概率，简单稳定的默认 = 长期 ROI 更高

---

## 五、文件变动一览

| 文件 | 操作 | 说明 |
|------|------|------|
| `scripts/fetch_es_for_mma.py` | **新建** | yfinance ES=F + VIX，增量 CSV |
| `scripts/fetch_spy_options.py` | **新建** | yfinance SPY 期权链，按腿查询 |
| `data/es_daily.csv` | **自动生成** | 首次运行脚本时创建 |
| `.cursor/commands/mma-1-analyze.md` | **修改** §2 | 替换 fetch_spy → fetch_es |
| `.cursor/commands/mma-3-verify.md` | **修改** §1 | 替换 fetch_spy → fetch_es，去掉 ratio 说明 |
| `.cursor/commands/mma-5-order-pro.md` | **修改** 7 处 | ① Phase 2 权利金验证 ② 删重复叠加层（保留表格版）③ IV 类型匹配（2 档）④ 半凯利仓位公式 ⑤ 决策推理链 ⑥ 券商核对字段（Breakeven/保证金）⑦ Greeks 防御性条款 ⑧ 主剧本单一聚焦 + 拒绝开仓条件 |
| `.cursor/commands/mma-6-advanced.md` | **新建** | Round 2 高级工具栈 slash command |
| `scripts/fetch_spy_for_mma.py` | **保留不动** | 旧版备用，mma-1/mma-3 改完后不再调用 |

---

## 六、执行顺序

```
Step 1  新建 scripts/fetch_es_for_mma.py（含 VIX 输出）
Step 2  新建 scripts/fetch_spy_options.py
Step 3  运行 fetch_es_for_mma.py --days 60 验证 CSV 生成、增量逻辑和 VIX 输出
Step 4  运行 fetch_spy_options.py 用一个真实例子验证输出格式和组合计算
Step 5  修改 mma-1-analyze.md（§2 替换）
Step 6  修改 mma-3-verify.md（§1 替换）
Step 7  修改 mma-5-order-pro.md（8 处：Phase 2 + 删重复 + IV + 半凯利 + 推理链 + 核对字段 + Greeks + 主剧本聚焦）
Step 8  新建 mma-6-advanced.md
Step 9  端到端验证：跑一次 /mma-3-verify，确认 ES + VIX 数据正常输出
```

---

## 七、需要确认的风险点

1. **`ES=F` 的连续合约换月**：yfinance 在合约换月（如从 ESM26 切 ESU26）时，历史数据会出现一个价格跳空。`es_daily.csv` 里会保留这个跳空，不做人工拼接。这是否可接受？

2. **期权脚本的调用时机**：`fetch_spy_options.py` 在盘后调用时返回的是收盘快照，隔天开盘后价格可能显著变化。提示词里已加了"下单前以实盘报价为准"的警告，是否够用？还是需要更强的警示？
