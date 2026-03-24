# 策略切换功能实施方案

## 整体思路

在 `main.py` 中使用 `importlib` 动态加载策略模块，将 `execute_day` 函数传递给 `backtest.py`，实现策略解耦。

## 改动范围

| 文件 | 操作 | 说明 |
|-----|------|------|
| `main.py` | 修改 | 读取 strategy 配置，动态加载策略 |
| `src/backtest.py` | 修改 | 接收 execute_day 函数作为参数 |
| `config/*.yaml` | 修改 | 新增 strategy 字段 |

## 实施步骤

### Step 1: 修改 main.py

新增动态加载策略逻辑：

```
1. 从场景配置读取 strategy 字段（默认 "baseline"）
2. 使用 importlib.import_module() 加载 src.strategies.{strategy}
3. 获取模块中的 execute_day 函数
4. 传递给 run_backtest()
```

关键代码思路：
```
strategy_name = config.get('strategy', 'baseline')
module = importlib.import_module(f'src.strategies.{strategy_name}')
execute_day = module.execute_day
```

打印策略名称：
```
print(f'使用策略：{strategy_name}')
```

### Step 2: 修改 backtest.py

将 `execute_day` 改为参数传入：

```
当前：from src.strategies.baseline import execute_day
改为：def run_backtest(data, fee_rate, orders, execute_day):
```

删除顶部的 import，改为通过参数接收。

### Step 3: 修改场景配置文件

在所有场景配置中新增 `strategy` 字段：

```yaml
strategy: "baseline"    # 新增
start_date: "2022-01-01"
...
```

需修改文件：
- `2022-bear.yaml`
- `2023-bull.yaml`
- `2022-2024-bear-bull.yaml`

## 验收清单

- [ ] main.py 支持动态加载策略
- [ ] backtest.py 通过参数接收 execute_day
- [ ] 场景配置文件新增 strategy 字段
- [ ] 运行时打印策略名称
- [ ] 默认使用 baseline（未指定时）
- [ ] 现有功能正常运行

