# 策略切换功能需求文档

## 1. 功能概述

实现策略动态切换功能，支持在场景配置文件中指定使用的策略，方便进行不同策略的对比实验。

## 2. 设计方案

### 2.1 策略接口

采用**函数式接口**，所有策略实现统一的函数签名：

```python
def execute_day(open_price, low_price, fee_rate, **kwargs):
    """
    执行单日交易逻辑
    
    Args:
        open_price: 当日开盘价
        low_price: 当日最低价
        fee_rate: 手续费率
        **kwargs: 策略特定参数（如 orders）
    
    Returns:
        成交订单列表
    """
```

### 2.2 配置方式

在**场景配置文件**中新增 `strategy` 字段，指定使用的策略：

```yaml
# config/2022-bear.yaml
strategy: "baseline"              # 策略名称（对应 src/strategies/{strategy}.py）
start_date: "2022-01-01"
end_date: "2022-12-31"
data_file: "data/SOXL_adjusted.csv"
fee_rate: 0.01
orders:                           # 策略参数，由策略自己解析
  - [1.00, 0.70]
  - [0.98, 0.40]
  - [0.95, 0.25]
  - [0.90, 0.15]
```

### 2.3 动态加载

`main.py` 或 `backtest.py` 根据配置文件中的 `strategy` 字段，动态加载对应的策略模块：

```
config 中 strategy: "baseline"
    ↓
动态加载 src/strategies/baseline.py
    ↓
调用 execute_day() 函数
```

## 3. 目录结构

```
src/strategies/
├── __init__.py
├── base.py                # 预留：未来可定义基类
├── baseline.py            # 基线策略（当前已实现）
└── {new_strategy}.py      # 后续新增的策略

docs/strategies/
├── baseline.md            # 基线策略说明
└── {new_strategy}.md      # 新策略说明
```

## 4. 技术要求

- 修改 `main.py` 或 `backtest.py`，支持动态加载策略
- 策略参数（如 orders）从配置文件传入，由策略自己解析
- 默认策略：`baseline`（如果配置文件未指定 strategy）

## 5. 验收标准

- [ ] 场景配置文件支持 `strategy` 字段
- [ ] 动态加载对应策略模块
- [ ] 运行时打印当前使用的策略名称
- [ ] 未指定 strategy 时默认使用 baseline
- [ ] 现有功能不受影响（向后兼容）
