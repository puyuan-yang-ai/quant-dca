# 订单分类统计实施方案

## 整体思路

1. 修改策略返回值，增加 `price_ratio` 字段用于区分订单类型
2. 在回测引擎中按 `price_ratio` 分类累计统计
3. 在主程序中输出分类统计结果

## 改动范围

| 文件 | 操作 | 说明 |
|-----|------|------|
| `src/strategies/baseline.py` | 修改 | 返回值增加 `price_ratio` 字段 |
| `src/backtest.py` | 修改 | 按 price_ratio 分类统计 |
| `main.py` | 修改 | 输出分类统计信息 |

## 实施步骤

### Step 1: 修改 baseline.py

在 `execute_day` 返回的订单中增加 `price_ratio` 字段：

```
当前返回：{'shares': 0.7, 'price': 42.5, 'cost': 30.1}
改为返回：{'shares': 0.7, 'price': 42.5, 'cost': 30.1, 'price_ratio': 1.0}
```

### Step 2: 修改 backtest.py

在 `run_backtest` 中新增分类统计字典：

```
order_stats = {
    1.0: {'shares': 0, 'cost': 0, 'count': 0},      # 市价单
    0.98: {'shares': 0, 'cost': 0, 'count': 0},     # 跌2%
    0.95: {'shares': 0, 'cost': 0, 'count': 0},     # 跌5%
    0.90: {'shares': 0, 'cost': 0, 'count': 0},     # 跌10%
}
```

遍历成交订单时，按 `price_ratio` 累加到对应分类。

返回结果中增加 `order_stats` 字段。

### Step 3: 修改 main.py

在"总持股数量"后面输出分类统计：

```
1. 遍历 result['order_stats']
2. 区分市价单（price_ratio=1.0）和限价单（price_ratio<1.0）
3. 限价单汇总 = 各子项之和
4. 档位描述：(1 - price_ratio) * 100 → "跌X%"
```

## 验收清单

- [ ] baseline.py 返回值包含 price_ratio
- [ ] backtest.py 返回 order_stats 分类统计
- [ ] main.py 输出格式符合 task.md 要求
- [ ] 现有功能正常运行

