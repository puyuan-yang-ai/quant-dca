# quant-dca 迁移到 WSL 开发环境方案

## 当前状态（2026-05-22 摸底结果）

| 项目 | Windows 侧 | WSL 侧 |
|------|-----------|--------|
| 路径 | `C:\Users\puyuyang\quant-dca` | `/home/puyuyang/Projects/quant-dca` |
| git commits | 14 个（最新：`0d94856 0515`） | 2 个（最新：`56adb3d`，落后 12 个） |
| `.venv` | 存在 | 不存在 |
| remote origin | `github.com/puyuan-yang-ai/quant-dca.git` | 同上 |

**结论**：WSL 里已有同名仓库，但代码严重落后。不需要重新克隆，只需要同步代码 + 重建 venv + 配置 Cursor Remote WSL。

---

## 迁移步骤

### 第 1 步：把 Windows 侧未推送的 commit 推到 GitHub

Windows 侧比 WSL 侧多 12 个 commit，先确保这些 commit 已推到 GitHub remote。

```powershell
# 在 Windows PowerShell / Cursor 终端里执行
cd C:\Users\puyuyang\quant-dca
git push origin main
```

确认推送成功后，Windows 侧的工作就完成了。

---

### 第 2 步：WSL 里拉取最新代码

```bash
# 在 WSL 终端里执行
cd ~/Projects/quant-dca
git pull origin main
```

拉取后用 `git log --oneline -5` 确认 commit 数量和 Windows 侧一致。

---

### 第 3 步：WSL 里重建 Python 虚拟环境

WSL 侧没有 `.venv`，需要重新创建并安装依赖。

```bash
cd ~/Projects/quant-dca

# 创建 venv
python3 -m venv .venv

# 激活
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

安装完成后验证：

```bash
python -c "import pandas; import yfinance; print('OK')"
```

---

### 第 4 步：配置 Cursor 用 Remote WSL 模式打开项目

这一步让 Cursor 直接编辑 WSL 里的文件，和 CC 操作的是同一份代码。

1. 确保 Cursor 已安装 **Remote - WSL** 扩展（搜索 `ms-vscode-remote.remote-wsl`）
2. 在 Cursor 里按 `Ctrl+Shift+P`，输入 `WSL: Open Folder in WSL`
3. 选择 `/home/puyuyang/Projects/quant-dca`

或者直接在 WSL 终端里运行：

```bash
cd ~/Projects/quant-dca
cursor .
```

Cursor 会自动以 Remote WSL 模式打开。

---

### 第 5 步：在 WSL 里启动 CC 开始开发

```bash
cd ~/Projects/quant-dca
claude
```

---

## 注意事项

### Windows 侧仓库怎么处理？

迁移完成后，Windows 侧的 `C:\Users\puyuyang\quant-dca` 可以**保留但停止直接编辑**，作为备份。后续所有开发在 WSL 侧进行，通过 git push/pull 保持同步。

### CC 运行验证（已完成）

- `claude --version`：✅ `2.0.42 (Claude Code)`
- AMD LLM Gateway 连通性：✅ API 可正常调用

### WSL 发行版

Ubuntu 22.04.5 LTS，Python 3.10.12，磁盘空间充足（946G 可用）。

### systemd warning 可忽略

每次运行时会出现 `wsl: Failed to start the systemd user session`，这是 WSL 配置问题，**不影响 CC 和开发工作**。
