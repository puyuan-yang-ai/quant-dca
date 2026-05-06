# 计划：Market Breadth 背离信号实现

## 实施步骤

### Step 1：背离检测算法

**文件**：新建 `src/breadth_divergence.py`（或在现有模块中添加）

算法流程：

1. 加载 Breadth 和 SPY 价格数据，按日期对齐
2. 识别 Swing Low：某天的值比前后各 N 天（N=5）都低 → 标记为局部低点
3. 筛选触发区域：只保留 Breadth < 25 的低点
4. 背离检测：对相邻两个 Breadth 低点（A 在前，B 在后），如果：
   - SPY 价格：B 处 < A 处（价格创新低）
   - Breadth：B 处 > A 处（Breadth 未新低）
   - → 在 B 处标记背离信号
5. 输出：背离日期集合 + 背离详情（用于图表画线）

### Step 2：Entry 模块

**文件**：`src/modules/entry.py`

- 新增 `BreadthDivergenceEntry` 类
- 构造时预计算所有背离日期（与 BreadthEntry、VIXEntry 相同的模式）
- `should_market_buy()`：当天存在背离信号时返回 True

### Step 3：信号比较

**文件**：`scripts/compare_signals.py`

- 新增 `--mode breadth-div` 用于单独测试
- 更新 `--mode full` 加入 BreadthDivergenceEntry
- 用成本优势比评估，加入全量排名

### Step 4：图表可视化

**文件**：`src/interactive_chart.py`、`scripts/show_chart.py`

在 Breadth 副图上：
- 背离点画三角标记（向上箭头）+ 文字（如 "Div"）
- 两个低点之间画连线（Breadth 连线 + 对应的价格连线可选）

数据传递：`show_chart.py` 计算背离数据 → 传入 `show_interactive_chart()` → JS 渲染

### Step 5：文档更新

- 更新 `docs/ground-truth.md`：加入 BreadthDivergenceEntry 的比较结果
- 更新 `CLAUDE.md`：Entry 模块列表、图表说明

## 变更文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/breadth_divergence.py` | 新增 | 背离检测算法 |
| `src/modules/entry.py` | 修改 | 新增 BreadthDivergenceEntry |
| `scripts/compare_signals.py` | 修改 | 新增 --mode breadth-div，更新 full |
| `src/interactive_chart.py` | 修改 | Breadth 副图画背离标记 + 连线 |
| `scripts/show_chart.py` | 修改 | 计算并传递背离数据 |
| `docs/ground-truth.md` | 修改 | 加入比较结果 |
| `CLAUDE.md` | 修改 | 更新模块列表和图表说明 |
