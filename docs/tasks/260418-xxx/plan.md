# 实施方案：交互式策略图表查看器

## 技术选型

### 选定方案：lightweight-charts-python

`lightweight-charts-python` 是对 TradingView 官方开源库 Lightweight Charts 的 Python 封装，`pip install lightweight-charts` 即可使用。

**选择理由：**

- 原生金融 K 线图，交互体验与 TradingView 一致（缩放/平移/十字光标/Y 轴自动跟随）
- 纯 Python 调用，无需编写 HTML/JS/CSS
- `chart.set(df)` 直接接受 DataFrame，与项目现有 CSV 数据格式（date, open, high, low, close）完全兼容
- `chart.marker()` API 支持在图上标注买卖信号
- 支持 EMA 等叠加指标（`Line` 系列）和多面板子图
- 开发量极小（基础图表约 10 行代码）

### 淘汰方案

| 方案 | 淘汰原因 |
|------|----------|
| Plotly/Dash | Y 轴不随 X 轴缩放自动调整（2017 年至今的已知问题），做看盘体验差；Dash 回调机制增加不必要的复杂度 |
| Bokeh | 无原生 K 线图类型，需手动用矩形+线段拼装，开发量大且维护成本高 |
| Lightweight Charts (原生 JS) | 需要搭建前后端架构，对纯 Python 项目而言过重；Python 封装已覆盖当前需求 |

### 风险提示

`lightweight-charts-python` 为单人维护项目（GitHub ~2k stars），但底层 Lightweight Charts JS 库由 TradingView 官方维护，渲染引擎稳定。如该 Python 封装停止维护，可考虑社区 fork 或迁移至原生 JS 方案。

## 环境准备

### 当前状态

- 宿主机 Python 3.10.12（`/usr/bin/python3`），系统级安装，无虚拟环境
- GTK3 系统库已安装（`libgtk-3-0`），`pywebview` 所需的系统依赖基本满足
- 无 conda/miniforge 环境

### 运行环境决策：宿主机 + venv

**淘汰方案：Docker 容器**

`lightweight-charts` 通过 `pywebview` 弹出本地浏览器窗口展示图表。若在容器内运行，需要做端口映射 + 改用 HTTP 服务模式，增加不必要的复杂度。宿主机直接运行体验最好。

**淘汰方案：conda / miniforge**

本项目依赖简单（`pyyaml`、`matplotlib`、`lightweight-charts`），全部可通过 pip 安装，无需 conda 管理跨语言编译依赖。Python 自带的 `venv` 模块已足够，且无任何商业许可问题。

### 执行命令

```bash
cd /home/puyuyang/project/study/quant-dca
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install lightweight-charts
```

更新 `requirements.txt`，添加 `lightweight-charts`。激活方式：每次进入项目时执行 `source .venv/bin/activate`。

## 实施步骤

### 第一步：基础 K 线图

新建 `src/interactive_chart.py`，实现基础功能：

- 加载 SOXL CSV 数据为 DataFrame
- 用 `chart.set(df)` 渲染 K 线图
- 验证缩放/平移/十字光标是否正常工作

### 第二步：叠加技术指标

- 在 K 线图上叠加 EMA 线（复用 `src/indicators.py` 的计算逻辑）
- 添加偏离度等已有指标作为副图面板

### 第三步：策略信号标注

- 对接 `BacktestEngine` 的回测结果数据
- 用 `chart.marker()` 在图上标注：
  - DCA 买入信号（各档位用不同颜色/形状区分）
  - 止盈触发点
  - SMH 利润分流事件

### 第四步：集成到回测流程

- 在现有回测流程中添加可选的交互式图表展示入口
- 保持 `save_chart()`（静态图）不变，新增 `show_interactive_chart()` 函数
- 可通过命令行参数或配置控制是否启用交互式图表

## 预估工作量

整体开发量约 50-80 行 Python 代码（不含空行和注释），难度低，属于增量式添加，不需要改动现有架构。
