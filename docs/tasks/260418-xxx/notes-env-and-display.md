# 知识点梳理：运行环境与图表显示

## 1. Python 虚拟环境方案对比

### venv（Python 内置）

- Python 3.3+ 标准库自带，`python3 -m venv .venv` 即可创建
- 隔离 Python 包，不隔离系统库
- 完全开源，无商业许可问题
- **适用场景：** 依赖都能通过 pip 安装的项目（纯 Python 包、或带预编译 wheel 的包）

### conda / miniconda

- 跨语言包管理器，能同时管理 Python 包和 C/Fortran 等系统级依赖
- miniconda 是 Anaconda 的精简版，由 Anaconda Inc. 维护
- **2024 年起 Anaconda 收紧商业许可**，200 人以上企业需付费使用 miniconda 及默认 channel
- **适用场景：** 需要装 PyTorch + CUDA、numpy/scipy 编译版、跨平台科学计算等复杂依赖链

### miniforge

- 社区维护的 conda 替代品，默认使用 conda-forge 频道（完全开源）
- 功能与 miniconda 基本一致，但不受 Anaconda 商业许可限制
- 内置 mamba（C++ 实现的 conda，解析依赖更快）
- **适用场景：** 需要 conda 的功能但不能使用 miniconda 的企业环境

### 怎么选？

```
项目依赖简单（纯 pip 包）？ → venv
需要管理 CUDA/C++/Fortran 等系统级依赖？ → miniforge
```

本项目（quant-dca）依赖仅 `pyyaml`、`matplotlib`、`lightweight-charts`，全是 pip 包，用 venv 即可。

## 2. 容器 vs 虚拟环境

| 维度 | Docker 容器 | Python venv |
|------|------------|-------------|
| 隔离范围 | 整个操作系统环境 | 仅 Python 包 |
| 系统库 | 容器内独立安装，不影响宿主 | 共用宿主机系统库 |
| GUI 程序 | 不方便，需额外配置（X11 转发/端口映射） | 直接使用宿主机的显示系统 |
| 适合场景 | 服务部署、环境完全隔离、CI/CD | 本地开发、脚本运行 |

**本项目为什么不适合跑在容器里？**

`lightweight-charts` 的显示机制是通过 `pywebview` 调用本地 GUI（GTK + WebKit）弹出一个窗口来渲染图表。在容器内：
- 容器默认没有 GUI 环境（无 X11 display）
- 要么做 X11 socket 转发（配置繁琐）
- 要么改用 HTTP 服务模式 + 端口映射，在宿主浏览器打开（可行但增加复杂度）

而在宿主机上直接跑，`pywebview` 弹窗即开即用，零额外配置。

## 3. lightweight-charts 的显示原理

```
Python 代码
  → lightweight-charts-python（Python 封装层）
    → pywebview（Python GUI 库）
      → GTK3 + WebKit2（系统 GUI 框架）
        → 弹出一个本地窗口，内嵌 WebView
          → 在 WebView 里加载 Lightweight Charts JS 库
            → 渲染交互式 K 线图
```

所以它本质上是：**Python 提供数据 → 本地窗口里跑一个迷你浏览器 → 浏览器里渲染 TradingView 图表**。

这就是为什么它需要 GTK/WebKit 系统库，也是为什么在无 GUI 的容器里跑不方便的原因。

## 4. pywebview 的系统依赖（Linux）

`pywebview` 在 Linux 上需要以下系统库：

- `libgtk-3-0` — GTK3 图形界面工具包
- `libwebkit2gtk-4.0` — WebKit2 渲染引擎（在 GTK 窗口里显示网页内容）
- `gobject-introspection` — GObject 类型系统的 Python 绑定支持

当前宿主机已安装 GTK3（`libgtk-3-0`）。如果运行时报 WebKit 相关错误，需要补装：

```bash
sudo apt install libwebkit2gtk-4.0-37 gir1.2-webkit2-4.0
```
