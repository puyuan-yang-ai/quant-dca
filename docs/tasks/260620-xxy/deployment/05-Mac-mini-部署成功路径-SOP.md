# Mac mini 部署成功路径 SOP

> 适用对象：第一次接触本项目的人，按本文可以把 `quant-dca` 部署到 Mac mini，并让它每天自动生成 SPY 预测报告后推送到 Telegram。
>
> 本文是基于 2026-07-18 在 `/Users/puyuan/Projects/quant-dca` 上真实跑通的流程整理。当前部署分支为 `feat/czsc-chan`。

## 0. 最终目标

部署完成后，Mac mini 会做到：

1. 每天早上 09:00 由 macOS `launchd` 自动触发。
2. 自动更新模型所需数据：
   - `data/SPY_adjusted.csv`
   - `data/vix_daily.csv`
   - `data/sp500_breadth.csv`
3. 自动运行模型推理，生成 `output/daily_prediction.json`。
4. 自动生成 Markdown 报告到 `reports/`。
5. 自动把报告通过 Telegram 推送出去。
6. 如果 Breadth 数据没有完整拉齐，则停止当天报告，并发送失败告警。

## 1. 当前已验证的关键结论

### 1.1 GitHub SSH

仓库地址：

```bash
git@github.com:puyuan-yang-ai/quant-dca.git
```

验证 SSH 是否可用：

```bash
ssh -T git@github.com
```

成功时会看到类似：

```text
Hi puyuan-yang-ai! You've successfully authenticated, but GitHub does not provide shell access.
```

这说明 SSH key 已经和 GitHub 账号配对成功，可以用 SSH 克隆或拉取仓库。

### 1.2 运行环境

项目目录：

```bash
/Users/puyuan/Projects/quant-dca
```

Python 虚拟环境：

```bash
/Users/puyuan/Projects/quant-dca/.venv
```

定时任务：

```bash
~/Library/LaunchAgents/com.quant.daily.plist
```

### 1.3 模型真实数据依赖

当前日报模型只依赖三类数据：

```text
SPY
VIX
S&P 500 Breadth
```

对应文件：

```text
data/SPY_adjusted.csv
data/vix_daily.csv
data/sp500_breadth.csv
```

当前日报推理不需要：

```text
data/SOXL_adjusted.csv
data/SMH_adjusted.csv
data/safe_haven.csv
```

这些数据不要放进每日任务，避免增加不必要的网络请求和失败概率。

### 1.4 Yahoo Finance 访问方式

当前 Mac mini 没有使用新加坡代理。

代码里存在：

```python
CurlSession(impersonate="chrome")
```

这只是模拟 Chrome 的 TLS/HTTP 请求指纹，不等于走代理，也不会改变出口 IP。

只有在 `.env` 或系统环境变量里配置了下面变量时，才会走代理：

```text
YAHOO_PROXY
HTTP_PROXY
HTTPS_PROXY
```

因此，如果新加坡服务器后续注销，只要 Mac mini 没有配置这些代理变量，当前部署不会受影响。

## 2. 一台新 Mac mini 从零部署

### 2.1 准备项目工作区

```bash
mkdir -p /Users/puyuan/Projects
cd /Users/puyuan/Projects
```

### 2.2 克隆仓库

```bash
git clone git@github.com:puyuan-yang-ai/quant-dca.git
cd /Users/puyuan/Projects/quant-dca
git checkout feat/czsc-chan
```

检查当前分支：

```bash
git status --short --branch
```

预期看到：

```text
## feat/czsc-chan...origin/feat/czsc-chan
```

### 2.3 安装系统依赖

先检查 Homebrew：

```bash
brew --version
```

如果没有 Homebrew，先安装：

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

安装 XGBoost 在 macOS 上需要的运行库：

```bash
brew install libomp
```

解释：`xgboost` 在 Mac 上会依赖 `libomp.dylib`。如果缺少它，模型推理阶段通常会报动态库加载失败。

### 2.4 创建 Python 虚拟环境

```bash
cd /Users/puyuan/Projects/quant-dca
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

验证关键依赖：

```bash
python -c "import pandas, sklearn, xgboost, yfinance, lxml; print('ok')"
```

成功时输出：

```text
ok
```

## 3. 配置 Telegram

### 3.1 准备两个字段

Telegram 推送需要：

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

`TELEGRAM_BOT_TOKEN` 来自 BotFather。

`TELEGRAM_CHAT_ID` 可以通过下面方式获取：

1. 先给自己的 Telegram bot 发一条消息，例如 `hi`。
2. 在终端执行：

```bash
curl -s "https://api.telegram.org/bot<你的TOKEN>/getUpdates"
```

3. 在返回 JSON 里找到：

```text
"chat":{"id":数字}
```

这个数字就是 `TELEGRAM_CHAT_ID`。

### 3.2 写入 `.env`

在项目根目录创建 `.env`：

```bash
cd /Users/puyuan/Projects/quant-dca
nano .env
```

内容格式：

```text
TELEGRAM_BOT_TOKEN=这里填真实token
TELEGRAM_CHAT_ID=这里填真实chat_id
```

保存后验证 `.env` 是否被 Git 忽略：

```bash
git check-ignore -v .env
```

预期会看到 `.gitignore` 命中 `.env`。这代表 token 不会被提交到 Git。

### 3.3 测试 Telegram 推送

```bash
. .venv/bin/activate
python -m ml.notify --text "quant-dca Telegram test"
```

成功时终端会显示：

```text
[Notify] Telegram 推送成功
```

并且 Telegram 会收到测试消息。

## 4. 数据更新 SOP

### 4.1 推荐入口：统一增量更新

```bash
. .venv/bin/activate
python scripts/update_market_data.py
```

这个脚本是日常运行的唯一推荐入口。它会一次性更新模型需要的三类数据：

```text
data/SPY_adjusted.csv
data/vix_daily.csv
data/sp500_breadth.csv
```

日常默认策略：

1. 读取本地 CSV 的最新日期。
2. 从最新日期往前覆盖 `7` 个自然日，向 Yahoo Finance 轻量拉取。
3. 和本地完整历史合并。
4. 同日期用新数据覆盖，旧历史继续保留。
5. 如果本地已经是 Yahoo 最新交易日，最终行数通常不变。

注意：这里的“覆盖 7 天”不是只保留 7 天数据，而是保留完整历史，只刷新最近几天，防止数据源后续修正最近 OHLCV。

可以手动指定 overlap：

```bash
python scripts/update_market_data.py --overlap-days 3
```

如果需要从零重建，可以显式全量：

```bash
python scripts/update_market_data.py --full
```

日常任务不要使用 `--full`。

### 4.2 SPY / VIX 的增量逻辑

SPY 和 VIX 都是单标的，增量逻辑比较直接：

1. 读取 CSV 最新日期。
2. 计算下载起点：

```text
下载起点 = 本地最新日期 - overlap_days
```

3. 从 Yahoo 拉取这个轻量窗口。
4. 合并回原 CSV。
5. 按日期去重，重复日期保留新值。

例如本地最新日期是 `2026-07-15`，`overlap-days=7`，则会从 `2026-07-08` 开始拉取。最后 CSV 仍然保留 1993 年以来的完整 SPY 历史，只是最近几天被刷新。

### 4.3 Breadth 的增量逻辑

Breadth 分成两层：下载层和汇总计算层。

下载层：

1. 从 Wikipedia 读取当前 S&P 500 成分股列表。
2. 每只成分股独立检查本地缓存最新日期。
3. 如果该股票缓存已经到 SPY 最新交易日，则跳过。
4. 如果该股票缓存落后，则只从它自己的最新日期往前覆盖 `7` 天开始拉取。
5. 如果是新成分股、缓存不存在或缓存损坏，则从较早日期补齐。
6. 分批下载，每个批次有硬超时。
7. 批次失败后使用指数退避重试。

成员股缓存目录：

```text
data/breadth_members/
```

汇总计算层：

1. 从本地 `data/breadth_members/*.csv` 读取最近计算窗口。
2. 默认用 `90` 个自然日作为本地计算前置窗口。
3. 用本地数据计算 MA20 和连续低于 MA20 的天数。
4. 重新生成最近窗口内的 Breadth 结果。
5. 合并回 `data/sp500_breadth.csv`，保留完整历史。

解释：下载只需要补缺口，但计算 MA20 不能只看缺失那几天。MA20 至少需要 20 个交易日上下文，连续弱势指标也需要前置状态。因此这里采用“网络下载轻量化，本地计算保守化”的做法。

解释：Breadth 是模型特征之一。如果只拿到部分成分股，算出来的 Breadth 会失真。这里宁可当天停止报告，也不要用不完整特征生成误导性预测。

### 4.4 Breadth 成功标志

成功时会看到类似：

```text
[Breadth] 成员股: 503 只，跳过 503 只，需更新 0 只
成功加载 503 只成员股缓存，最新日期 2026-07-17
[Breadth] 完成: 8422 行，最新 2026-07-17
[MarketData] SPY=2026-07-17 VIX=2026-07-17 Breadth=2026-07-17
```

可以检查最新日期：

```bash
tail -5 data/sp500_breadth.csv
```

## 5. 手动跑完整链路

部署前必须手动跑一次：

```bash
cd /Users/puyuan/Projects/quant-dca
bash scripts/run_daily.sh
```

这个脚本会依次执行：

1. 检查网络是否可用。
2. 统一增量更新 SPY / VIX / Breadth。
3. 运行模型推理。
4. 生成报告。
5. 推送 Telegram。

成功时会看到：

```text
========== 每日推理完成 ==========
```

同时日志里会有：

```text
[Report] 报告已生成: /Users/puyuan/Projects/quant-dca/reports/YYYY-MM-DD.md
[Notify] Telegram 推送成功
```

检查输出：

```bash
ls -lh output/daily_prediction.json
ls -lh reports/
```

## 6. 安装 launchd 定时任务

### 6.1 确认 plist 内容

项目里的 plist：

```bash
deploy/com.quant.daily.plist
```

关键配置应该是：

```text
ProgramArguments: /bin/bash /Users/puyuan/Projects/quant-dca/scripts/run_daily.sh
WorkingDirectory: /Users/puyuan/Projects/quant-dca
StartCalendarInterval: Hour 9, Minute 0
```

检查语法：

```bash
plutil -lint deploy/com.quant.daily.plist
```

### 6.2 安装到 LaunchAgents

```bash
mkdir -p ~/Library/LaunchAgents
cp deploy/com.quant.daily.plist ~/Library/LaunchAgents/com.quant.daily.plist
plutil -lint ~/Library/LaunchAgents/com.quant.daily.plist
```

### 6.3 加载任务

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.quant.daily.plist
```

如果之前已经加载过，可能会报 `Bootstrap failed: 5`。先卸载再加载：

```bash
launchctl bootout gui/$(id -u)/com.quant.daily
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.quant.daily.plist
```

### 6.4 查看任务状态

```bash
launchctl print gui/$(id -u)/com.quant.daily | grep -E "state|runs|last exit|Hour|Minute|working directory"
```

正常情况下会看到：

```text
state = not running
Hour = 9
Minute = 0
working directory = /Users/puyuan/Projects/quant-dca
```

解释：`state = not running` 是正常的。它表示当前没在执行，等每天 09:00 到了才会启动。

### 6.5 手动触发 launchd 任务

如果想确认 launchd 能调起脚本：

```bash
launchctl kickstart -k gui/$(id -u)/com.quant.daily
```

然后查看日志：

```bash
tail -100 logs/launchd.out.log
tail -100 logs/launchd.err.log
```

## 7. 日志和排障

### 7.1 每日主日志

脚本自己的日志按日期保存：

```text
logs/daily_YYYYMMDD.log
```

查看当天日志：

```bash
tail -200 logs/daily_$(date +%Y%m%d).log
```

### 7.2 launchd 日志

launchd 标准输出：

```text
logs/launchd.out.log
```

launchd 标准错误：

```text
logs/launchd.err.log
```

### 7.3 常见失败：GitHub SSH 不通

现象：

```text
Permission denied (publickey).
```

处理：

```bash
ls -la ~/.ssh
ssh -T git@github.com
```

如果仍失败，需要把 Mac mini 的 SSH 公钥加入 GitHub。

### 7.4 常见失败：XGBoost 缺 libomp

现象：

```text
Library not loaded: ... libomp.dylib
```

处理：

```bash
brew install libomp
```

### 7.5 常见失败：Telegram 没收到

检查 `.env`：

```bash
git check-ignore -v .env
python -m ml.notify --text "telegram test"
```

如果 `getUpdates` 没有 chat id，通常是因为还没有先给 bot 发过消息。

### 7.6 常见失败：Breadth 拉不齐

现象：

```text
更新 Breadth 数据失败
```

处理顺序：

```bash
tail -200 logs/daily_$(date +%Y%m%d).log
find data/breadth_members -type f | wc -l
python scripts/update_market_data.py
```

解释：Breadth 失败后当天报告会停止，这是预期行为。不要绕过这个检查，因为不完整 Breadth 会导致模型特征失真。

## 8. 已验证成功样例

2026-07-18 的真实验证结果：

```text
Market data:
[SPY] 增量(last=2026-07-17, overlap=7d): 从 2026-07-10 拉取
[VIX] 增量(last=2026-07-17, overlap=7d): 从 2026-07-10 拉取
[Breadth] 成员股: 503 只，跳过 503 只，需更新 0 只
[MarketData] SPY=2026-07-17 VIX=2026-07-17 Breadth=2026-07-17

Daily run:
步骤 1/4: 增量更新市场数据
步骤 2/4: 模型推理
步骤 3/4: 生成报告
步骤 4/4: Telegram 推送
========== 每日推理完成 ==========
```

生成报告：

```text
reports/2026-07-17.md
```

数据新鲜度：

```text
SPY: 2026-07-17
VIX: 2026-07-17
breadth: 2026-07-17
```

## 9. 给 OpenClaw Skill 的执行边界

后续如果把本文沉淀成 OpenClaw skill，建议 skill 只做这些动作：

当前已创建的 OpenClaw skill 位置：

```text
/Users/puyuan/.openclaw/workspace/skills/quant-dca-daily-report/SKILL.md
```

1. 进入固定项目目录：

```bash
cd /Users/puyuan/Projects/quant-dca
```

2. 确认当前分支和工作区状态：

```bash
git status --short --branch
```

3. 确认 `.env` 存在但不打印内容：

```bash
test -f .env
git check-ignore -v .env
```

4. 执行每日脚本：

```bash
bash scripts/run_daily.sh
```

5. 根据退出码判断：
   - 退出码 `0`：成功。
   - 非 `0`：失败，读取 `logs/daily_YYYYMMDD.log` 摘要，并确保 Telegram 失败告警已尝试发送。

当前推荐的成功路径是：

```bash
bash scripts/run_daily.sh --no-notify
.venv/bin/python scripts/format_telegram_report.py --threshold 0.5
```

第一条命令负责数据更新、推理、本地报告和失败告警。第二条命令负责把 `output/daily_prediction.json` 渲染成 Telegram 友好的完整解释版报告。成功报告由 OpenClaw 通过自身 Telegram/message 通道发送，避免底层脚本和 Skill 重复推送。

不建议 skill 做这些事：

1. 不要打印 `.env` 内容。
2. 不要绕过 Breadth 完整性检查。
3. 不要在数据未拉齐时强行运行模型。
4. 不要自动修改 Git 远程地址或 SSH key。
5. 不要自动提交含密钥、缓存、临时文件的内容。

## 10. 维护命令速查

重新跑一次完整链路：

```bash
cd /Users/puyuan/Projects/quant-dca
bash scripts/run_daily.sh
```

查看定时任务：

```bash
launchctl print gui/$(id -u)/com.quant.daily
```

卸载定时任务：

```bash
launchctl bootout gui/$(id -u)/com.quant.daily
```

重新加载定时任务：

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.quant.daily.plist
```

查看当天日志：

```bash
tail -200 logs/daily_$(date +%Y%m%d).log
```

查看最新报告：

```bash
ls -lt reports/ | head
```
