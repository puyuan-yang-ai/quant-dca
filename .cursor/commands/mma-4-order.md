---
description: 基于最新剧本状态，生成 SPY Spread 期权订单参数（老虎证券组合单）
argument-hint: <scenario_evolution.md 绝对路径，支持 @workspace/...>
---

## 参数校验（最高优先级，必须先执行）

`$ARGUMENTS` 应为 `YYYYMMDD_scenario_evolution.md` 文件的绝对路径。若以 `@workspace/` 开头，先把它替换为 `/home/puyuyang/workspace/`；规范化后仍非 `/` 开头则停止执行，回复：

如果 `$ARGUMENTS` 为空或未提供，请立即停止执行，并仅回复以下提示，不要执行任何后续步骤：

> ⚠️ 缺少必需参数：请提供 `<scenario_evolution.md 的绝对路径>` 后重新触发。

## 任务

请读取 `$ARGUMENTS` 指向的剧本推演文件，以该文件中**最新的剧本状态**（最后一次 ✅ / ⚠️ / ❌ 校验结果）作为唯一判断依据，生成可在老虎证券（Tiger Brokers）直接执行的 SPY 期权组合单订单参数。

完成后，请将订单参数落盘为以下 Markdown 文件，**放置在与 `$ARGUMENTS` 同一目录下**，文件名使用系统当前时刻命名：

- `YYYYMMDD_HHMM_orders.md`：YYYYMMDD 为今日日期，HHMM 为触发时刻（24 小时制）。每次触发都生成独立新文件，不覆盖历史。

### 要求

- 标的：SPY（SPDR S&P 500 ETF）
- 策略：两腿 Spread 期权组合单，由 AI 根据当前剧本方向判断选择合适的 Spread 类型：
  - 看多：Bull Call Spread 或 Bull Put Spread
  - 看空：Bear Put Spread 或 Bear Call Spread
- 不做四腿及以上的复杂结构
- 若当前主剧本状态为 ❌ 已失效，请明确说明，不生成订单参数，等待新的剧本判断（此时不落盘订单文件）

### 输出格式

请严格按照以下参数清单格式输出，每个策略方案独立一块：

---

**策略名称**：（如 Bull Call Spread）
**方向判断**：做多 / 做空
**当前依据**：（一句话说明当前触发此策略的核心逻辑）

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
**建议仓位**：X 组（占总资金约 X%）
**止损条件**：（具体触发条件，如 SPY 跌破 $XXX 或组合亏损超过 X%）
**止盈条件**：（具体触发条件，如 SPY 涨至 $XXX 或盈利达到 X%）

---

### 附加说明

- 到期日的选择需匹配 MMA 周报中的关键时间窗口，避免在重要转折点前过早到期
- 行权价的选择需结合当前关键支撑位和阻力位
- 如有多个策略方案，按"概率 × 盈亏比"排序，优先展示最推荐的方案
- 落盘文件路径必须与 `$ARGUMENTS` 在同一目录
