---
description: Round 2 升级评估——基于 mma-4 已输出的订单，评估是否升级到 Long Call+BPS、Diagonal 或 Short DTE Long Call 等高级结构
argument-hint: <mma-4 已生成的 orders.md 绝对路径，支持 @workspace/...>
---

## 参数校验（最高优先级，必须先执行）

`$ARGUMENTS` 应为 `mma-4-order` 已生成的 `YYYYMMDD_HHMM_orders.md` 文件的绝对路径。若以 `@workspace/` 开头，先把它替换为 `/home/puyuyang/workspace/`；规范化后仍非 `/` 开头则停止执行。

如果 `$ARGUMENTS` 为空或未提供，请立即停止，回复：

> ⚠️ 缺少必需参数：请提供 `mma-4` 已生成的 `orders.md` 绝对路径后重新触发。

## 定位与使用时机

**Round 1（`mma-4-order`）默认只输出 Vertical Spread**，覆盖 70-80% 的 MMA 场景，已经足够。

**本命令（Round 2）仅在以下场景主动触发**：
- 你看完 mma-4 的订单，认为当前市场结构特别适合高级工具
- 你有明确的理由（时间窗精确 / 想保留上涨敞口 / 有强支撑需要叠加 Credit 补贴）
- 你愿意承担更复杂的退出管理

**不要随意触发本命令**：高级工具需要更多盘中关注，管理不当会让利润让回去。

---

## 任务

读取 `$ARGUMENTS` 指向的订单文件（mma-4 已生成的基础 Vertical Spread 方案），结合当前剧本状态，评估是否适合从以下 3 种高级结构中选择一种进行升级。

**升级前必须先运行（如尚未运行）**：

```bash
python scripts/fetch_spy_options.py --legs "<type,expiry,strike> ..."
```

获取高级工具涉及的所有腿的真实 bid/ask，**不允许用估算值输出高级工具方案**。

---

## 高级工具栈触发清单

| 工具 | 适用场景关键词 | 升级理由 |
|------|--------------|---------|
| **Long Call + Bull Put Spread**（看涨 3 腿混合）| "时间窗精确" + "想要上涨敞口" + "支撑明确" | BPS credit 补贴 Long Call debit，不同到期错配让 BPS 早归零 |
| **Diagonal Call Spread**（看涨 2 腿不同 DTE）| "上涨可能延伸" + "不想被短腿封顶" | Long Call 留住上涨敞口，Short Call 收 theta |
| **Short DTE Long Call**（裸单腿，极端自信）| "1-3 天内事件驱动" + "极度自信" | 极简暴力，但单笔仓位强制 ≤ 5% 期权预算（$95，约 $1,890 × 5%）|

---

## 响应格式（5 问结构，强制）

收到升级请求后，AI 必须针对用户选择的工具，按以下 5 问逐一回答（每问 2-4 句）：

1. **WHAT（是什么）**：升级后的完整结构（所有腿、Strike、DTE、方向、张数）
2. **WHY（为什么）**：升级目的（上涨敞口 / BPS 补贴 / Theta 收割），以及相比基础 Vertical 的具体优势
3. **HOW（怎么互动）**：与基础层的 Delta / Theta / Vega 净变化；是否存在方向冲突
4. **WHEN（怎么平）**：各腿独立退出规则 vs 联动退出规则，触发条件分别是什么
5. **WHAT IF（thesis 失败）**：基础层 + 高级层同时失败时，账户级别最大亏损合并计算

---

## DTE 配比口诀

### Long Call + Bull Put Spread

- **Long Call DTE** = thesis 关键日距今交易日数 + 5-7 天缓冲（按铁律 1 公式，与 mma-4 基础层一致）
- **Bull Put Spread DTE** = Long Call DTE 的 **50-70%**（让 BPS 早一点归零，credit 补贴 Long Call debit）
- **反面示例**：两腿同 DTE → BPS 没有足够时间衰减，到期归零时 Long Call 也归零，相互拖累

### Diagonal Call Spread

- **Long Call DTE**（买腿）：thesis 关键日 + 5-7 天缓冲
- **Short Call DTE**（卖腿）：Long Call DTE 的 50% 左右（先让短腿归零收 Theta，然后决定是否续滚）
- **重要**：Long Call 到期日必须 ≥ Short Call 到期日，否则变成反向 Diagonal（见下方警告）

---

## Diagonal 保证金规则（老虎证券）

老虎证券对 Diagonal 的判断方式：
- **Long Call 到期日 ≥ Short Call 到期日** 且 **Long Call Strike ≤ Short Call Strike** → 按"已覆盖"计算，**不需要额外保证金**，最大亏损 = 净 debit
- **下单前必查**：Tiger 下单页"组合保证金占用"栏
  - 显示 $0 或 = 净 debit → 安全，按已覆盖处理
  - 显示大额数字（如 strike 差 × 100）→ 被识别为裸卖，立即检查腿的方向和到期日

**Early Exercise 风险**：Short Call 到期前 1-2 天若 SPY 突破 Short Strike（深 ITM），可能被 Early Exercise，需要交付 100 股 SPY；此时券商会强制行权或卖出 Long Call 对冲。

---

## ⛔ 反向 Diagonal 绝对禁止

**Long 近期 + Short 远期的"反向 Diagonal"绝对禁止**——Long 到期后 Short 变成裸卖，无上限风险。

---

## 一票否决（满足任一条件立即拒绝升级）

1. ❌ 升级后净 delta ≈ 0（方向完全对冲）→ 支付双倍手续费，无意义
2. ❌ 涉及裸卖 Call / 裸卖 Put → 无上限风险，保证金陷阱
3. ❌ 老虎证券不支持该多腿结构 → 执行不可行
4. ❌ 升级后账户级别最大亏损 > 总资金 5%（$900）→ 仓位过重
5. ❌ Short DTE Long Call 单笔超过期权预算 5%（$95）→ 强制压回

---

## 输出要求

升级评估完成后，**不自动落盘**——由用户确认后，手动追加到原 `orders.md` 文件的独立区块，明确标注：

```
## Round 2 升级层（用户确认后追加）
工具：XXX
确认时间：YYYY-MM-DD HH:MM
```
