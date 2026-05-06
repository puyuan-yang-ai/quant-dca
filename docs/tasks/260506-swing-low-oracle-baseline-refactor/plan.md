# 计划：Swing Low 波段底部可视化

## Step 1：实现 swing low 检测函数

在 `src/` 下新增或在现有模块中添加 `detect_swing_lows(close_prices, dates, n)` 函数：

- 输入：收盘价列表、日期列表、窗口参数 N
- 逻辑：遍历 `[N, len-N)` 范围，检查 `close[i]` 是否严格小于左右各 N 天
- 输出：`[{'date': '2022-06-17', 'price': 373.87}, ...]`

## Step 2：修改交互式图表

修改 `src/interactive_chart.py`：

1. 新增 `swing_lows` 参数，接收两组数据（N=5 和 N=10）
2. 在 K 线主图上用 marker 标注：
   - N=5：颜色 A（如蓝色）
   - N=10：颜色 B（如红色/橙色）
3. 去掉 VIX 子图（保留 K 线 + RSI + Breadth）
4. 去掉 DCA 交易标记（买入/卖出箭头）

## Step 3：修改 show_chart.py 调用

修改 `scripts/show_chart.py`：

1. 调用 swing low 检测函数，分别用 N=5 和 N=10
2. 将结果传递给 `show_interactive_chart()`
3. 跳过 VIX 数据加载

## Step 4：运行验证（第一阶段完成）

```bash
bash show_chart.sh --env all
```

在浏览器中观察标注效果，确认 swing low 检测是否合理。

---

## Step 5（第二阶段）：最小跌幅过滤

在第一阶段确认 N 值后：

1. 实现 swing high 检测（与 swing low 对称，取局部最高点）
2. 对每个 swing low，找到其前方最近的 swing high，计算跌幅：`(high - low) / high`
3. 过滤掉跌幅 < X% 的 swing low（X 候选：3%、5%、7%）
4. 在图表上可视化过滤前后的差异，确定最终阈值

## Step 6（第二阶段）：Oracle 改造

1. 用过滤后的 swing low 底部日收盘价均价作为 Oracle 均价
2. 修改 `docs/ground-truth.md` 中 Oracle 极值的计算公式说明
3. 重新计算所有策略的 Oracle 极值和极值利用率
4. 更新 ground-truth.md 总表
