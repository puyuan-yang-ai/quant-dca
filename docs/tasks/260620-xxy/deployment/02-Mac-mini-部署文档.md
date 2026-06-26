# Mac mini 部署文档（照着敲）

> 用途：脚本写完、push 到 GitHub 之后，在 Mac mini 上照这份从上到下敲一遍，就能跑起来。
> 面向"终端命令用得不多"的你，每条命令都说明它在干啥。
> 配套：`00-心智模型.md`、`01-开发计划.md`。

## ⚠️ 前提（在你开始之前必须满足）

1. 脚本已写完，并且**已经 push 到 GitHub**（这步在开发机做，不在 Mac mini）。
2. 你的远程仓库是：`git@github-personal:puyuan-yang-ai/quant-dca.git`
   - 注意这里用了一个 SSH 别名 `github-personal`（在开发机的 `~/.ssh/config` 里配过）。
   - **Mac mini 上要么也配一样的 SSH 别名，要么改用标准地址** `git@github.com:puyuan-yang-ai/quant-dca.git`（见步骤 1 的说明）。
3. 当前开发分支是 `feat/czsc-chan`（不是 main）。clone 后记得切到包含这套脚本的分支。

---

## 步骤 0：装基础工具（Mac mini 上，只需一次）

```bash
# 检查是否已有 git 和 python3（macOS 一般自带，没有会提示安装命令行工具）
git --version
python3 --version
```

```bash
# 装 Homebrew（Mac 的软件包管理器，如果还没装）。已装可跳过。
# 官网命令，装完按提示把 brew 加进 PATH
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

```bash
# 装 libomp —— xgboost 在 Mac 上运行时依赖它，不装会报错。务必装。
brew install libomp
```

---

## 步骤 1：把项目拉下来

```bash
# 进到你想放项目的目录（举例放在用户主目录下）
cd ~

# 克隆仓库。两种地址二选一：
# (A) 如果你在 Mac mini 上配过 github-personal 这个 SSH 别名：
git clone git@github-personal:puyuan-yang-ai/quant-dca.git

# (B) 否则用标准 GitHub 地址（需要 Mac mini 的 SSH key 已加到 GitHub 账号）：
# git clone git@github.com:puyuan-yang-ai/quant-dca.git

# 进入项目目录
cd quant-dca

# 切到包含脚本的分支（脚本所在分支，按实际情况；若已合并到 main 则切 main）
git checkout feat/czsc-chan
```

---

## 步骤 2：重建 Python 环境（关键，不能跳过）

> 为什么要做：开发机的 `.venv` 是 Linux 的，Mac 用不了，必须重新建一份 Mac 的。

```bash
# 在项目目录里创建一个全新的虚拟环境，名字叫 .venv
python3 -m venv .venv

# 激活它（激活后命令行前面会出现 (.venv) 字样）
source .venv/bin/activate

# 升级 pip（可选，避免老版本装包出问题）
pip install --upgrade pip

# 按清单安装所有依赖（会装 pandas/xgboost/scikit-learn 等，首次较慢，耐心等）
pip install -r requirements.txt
```

装完验证一下关键库能导入：

```bash
# 能正常打印版本号说明装好了；报错说明缺库或 libomp 没装
python -c "import xgboost, pandas, sklearn; print('ok', xgboost.__version__)"
```

---

## 步骤 3：确认模型和历史数据都在

> 这些是随 git 一起拉下来的，确认一下别漏。

```bash
# 应该能看到 spy_nday5_v3.ubj 和 spy_nday5_v3.json
ls -la models/

# 应该能看到一堆 *.csv（SPY/VIX/breadth 等历史数据）
ls -la data/
```

如果 `data/` 是空的（比如当初没提交进 git），先手动全量拉一次：

```bash
# 仅当 data/ 缺数据时才需要跑这步
python scripts/fetch_daily_data.py
```

---

## 步骤 4：配置 Telegram 推送

> 先拿到 Telegram 的两个密钥，再写进 `.env` 文件。

### 4.1 拿 bot token（在手机/电脑的 Telegram 里操作）

1. 在 Telegram 搜索 `@BotFather`，开始对话。
2. 发送 `/newbot`，按提示给 bot 起名字。
3. 创建成功后，BotFather 会给你一串 **token**（形如 `123456:ABC-DEF...`），复制保存。

### 4.2 拿 chat id

1. 在 Telegram 里找到你刚建的 bot，给它**随便发一条消息**（比如 "hi"）。必须先发，否则下一步拿不到。
2. 在 Mac mini 终端运行（把 `<TOKEN>` 换成你的 token）：

```bash
# 拉取 bot 收到的消息，从里面找 chat.id
curl -s "https://api.telegram.org/bot<TOKEN>/getUpdates"
```

3. 在返回的 JSON 里找 `"chat":{"id": 数字}`，那个数字就是你的 **chat id**。

### 4.3 写进 .env 文件

```bash
# 在项目根目录创建 .env 文件（用任意编辑器，这里用 nano）
nano .env
```

在打开的编辑器里填入（替换成你的真实值）：

```
TELEGRAM_BOT_TOKEN=123456:ABC-DEF你的token
TELEGRAM_CHAT_ID=你的chatid数字
```

保存退出（nano 里按 `Ctrl+O` 回车保存，`Ctrl+X` 退出）。

> `.env` 已被 `.gitignore` 忽略，不会被提交，密钥安全。

---

## 步骤 5：手动跑一次，全链路验证（最关键的一步）

> 在装定时器之前，先手动证明整条链路能跑通。

```bash
# 确保 venv 还激活着（命令行前面有 (.venv)），然后跑总指挥脚本
bash scripts/run_daily.sh
```

预期结果：
- 终端能看到拉数据 → 推理 → 出报告 → 推送的过程
- `reports/` 下出现当天的 `.md` 报告
- **你的手机收到一条 Telegram 消息**

如果这步成功，自动化就基本成了。如果失败，看日志：

```bash
# 查看当天日志，定位卡在哪一步
ls -la logs/
cat logs/daily_*.log
```

---

## 步骤 6：装 launchd 定时器（设每天 08:00 的闹钟）

```bash
# 把项目里的 plist 配置复制到 macOS 规定的目录
cp deploy/com.quant.daily.plist ~/Library/LaunchAgents/

# 装载这个定时任务（gui/$(id -u) 表示当前登录用户）
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.quant.daily.plist

# 确认装上了：能看到 com.quant.daily 这一行就对了
launchctl list | grep quant
```

> 注：旧版 macOS 若 `bootstrap` 不支持，用 `launchctl load ~/Library/LaunchAgents/com.quant.daily.plist`。

### 想立刻测试一下定时任务（不用等到 08:00）

```bash
# 手动触发一次该任务，验证 launchd 调起来没问题
launchctl kickstart -k gui/$(id -u)/com.quant.daily
```

---

## 日常维护速查

### 模型更新后，怎么同步到 Mac mini
```bash
# 在开发机：重训 → 提交 → push（你自己做）
# 在 Mac mini：拉最新代码即可，模型文件会一起更新
cd ~/quant-dca
git pull
```

### 改运行时间 / 改成一天跑两次
```bash
# 1. 编辑 plist 里的 StartCalendarInterval
nano ~/Library/LaunchAgents/com.quant.daily.plist
# 2. 卸载再重装让改动生效
launchctl bootout gui/$(id -u)/com.quant.daily
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.quant.daily.plist
```

### 某天没收到推送，怎么排查
```bash
cd ~/quant-dca
cat logs/daily_$(date +%Y%m%d).log   # 看当天日志，多半是 fetch 失败或网络问题
```

### 暂停 / 恢复定时任务
```bash
# 暂停
launchctl bootout gui/$(id -u)/com.quant.daily
# 恢复
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.quant.daily.plist
```

---

## 常见坑速查

| 现象 | 可能原因 | 解决 |
| --- | --- | --- |
| `import xgboost` 报错 | 没装 libomp | `brew install libomp` |
| getUpdates 返回空 | 还没给 bot 发过消息 | 先在 Telegram 给 bot 发一条 |
| 手动跑成功但定时不跑 | plist 路径写的不是绝对路径 / 没装载 | 检查 plist、重新 launchctl 装载 |
| 早上没跑（Mac 关机过） | launchd 不补"关机"错过的 | 保持 Mac mini 常开，或加下午补跑点 |
| fetch 拉不到数据 | 网络问题 | 看日志；脚本会重试并推送告警 |
