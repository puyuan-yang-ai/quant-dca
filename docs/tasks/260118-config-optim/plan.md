# 多场景配置文件支持实施方案

## 整体思路

修改 `main.py` 的配置加载逻辑：先读取 `settings.yaml` 获取 `use_config` 字段，再加载对应的场景配置文件。

## 改动范围

| 文件 | 操作 | 说明 |
|-----|------|------|
| `main.py` | 修改 | 两步加载配置逻辑 |
| `config/settings.yaml` | 简化 | 仅保留 use_config 字段 |
| `config/2024-bull.yaml` | 新建 | 示例场景配置 |

## 实施步骤

### Step 1: 修改 main.py 配置加载逻辑

将现有的单文件加载改为两步加载：

```
1. 加载 settings.yaml -> 获取 use_config 值
2. 加载 config/{use_config} -> 获取实际回测参数
```

修改 `load_config()` 函数或在 `main()` 中增加逻辑：

```
config_dir = os.path.join(root_dir, 'config')
settings = load_config(os.path.join(config_dir, 'settings.yaml'))
scene_config_name = settings.get('use_config')
config = load_config(os.path.join(config_dir, scene_config_name))
```

打印信息增加场景配置文件名：
```
print(f'场景配置：{scene_config_name}')
```

### Step 2: 简化 settings.yaml

将现有内容替换为：

```yaml
# 指定使用的场景配置文件
use_config: "2024-bull.yaml"
```

### Step 3: 创建示例场景配置文件

将现有 settings.yaml 的内容迁移到 `config/2024-bull.yaml`：

```yaml
# 2024年牛市回测配置
start_date: "2024-07-11"
end_date: "2025-04-07"
data_file: "data/SOXL.csv"
fee_rate: 0.01
orders:
  - [1.00, 0.70]
  - [0.98, 0.40]
  - [0.95, 0.25]
  - [0.90, 0.15]
```

## 验收清单

- [ ] main.py 支持两步配置加载
- [ ] settings.yaml 简化为只有 use_config
- [ ] 创建 2024-bull.yaml 示例配置
- [ ] 运行时打印场景配置文件名
- [ ] 切换 use_config 后回测结果正确

