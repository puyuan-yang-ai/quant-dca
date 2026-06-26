# 方案：Mac mini 每日推理自动化

> 配套：同目录 `task.md`（需求与目标、决策记录）。
> 核心结论：**用 launchd 定时任务，不需要常驻进程。**

## 一、为什么不用常驻进程

用户曾考虑"持久化进程 + 定时触发"。对本场景属过度设计，区别如下：

| 方案 | 适用 | 本场景 |
| --- | --- | --- |
| 常驻进程（daemon） | 7×24 实时响应：API 服务、消息消费者、WebSocket | ❌ 不需要 |
| 定时任务（跑完即退） | 周期性批处理：每天/每小时一次 | ✅ 正解 |

需求是"每天跑一次推理"，是典型批处理。常驻进程 99% 时间在睡觉，徒增内存泄漏/崩溃无感知的风险。定时任务由系统到点拉起脚本，跑几秒退出，干净可靠。

## 二、为什么用 launchd 而非 cron

macOS 上两者都能定时，但结论是 **launchd**：

- **cron**：Mac 睡眠时错过的任务**不补跑**，Apple 已不推荐。
- **launchd** + `StartCalendarInterval`：睡眠期间错过的任务，**唤醒后会补跑**（多个权威来源一致）。Mac mini 会自动睡眠，这一点关键。

### launchd 的边界（必须知道）

1. **只补"睡眠"错过的，不补"关机"错过的**。关机期间错过的调度点，要等下一个调度点。用户的 Mac mini 基本常开，风险低。
2. **唤醒后立即触发，可能网络/时钟尚未就绪**。需脚本内做"等待 + 重试"兜底。
3. **launchd 启动脚本时环境变量近乎为空**（无 shell 的 PATH 等）。脚本内所有路径必须**绝对路径**，所需环境变量在脚本内显式设置。

## 三、整体数据流

```
北京时间每天 08:00（StartCalendarInterval: Hour=8, Minute=0）
        ↓  launchd 触发
   run_daily.sh（绝对路径、自带环境、带重试）
        ↓
   1. 激活 venv
   2. python scripts/fetch_daily_data.py   拉 SPY/VIX/breadth 最新日线
   3. python -m ml.predict --json output/daily_prediction.json
   4. python -m ml.report  读 JSON → 生成 Markdown 报告
   5. Telegram 推送摘要（含报告关键字段）
        ↓
   日志写入 logs/daily_YYYYMMDD.log，脚本退出
```

## 四、需要新增的产物

| 文件 | 作用 | 运行位置 |
| --- | --- | --- |
| `scripts/run_daily.sh` | 串联全流程，含 venv 激活、网络重试、错误捕获、日志 | Mac mini |
| `ml/report.py` | 读推理 JSON，渲染每日 Markdown 报告到 `reports/YYYY-MM-DD.md` | 通用 |
| `ml/notify.py`（或 sh 内函数） | Telegram sendMessage 推送 | Mac mini |
| `deploy/com.quant.daily.plist` | launchd 配置：每天 08:00 触发 run_daily.sh | Mac mini |
| `.env`（不进 git） | `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`（按需 `YAHOO_PROXY`） | Mac mini |

## 五、关键实现要点

### run_daily.sh
- `#!/bin/bash`，`set -euo pipefail`。
- 全部绝对路径（项目根、venv、python）。
- 开头 `sleep` 几秒 + 简单网络探测（如 `curl` Yahoo），失败则重试数次，避免唤醒即跑网络未就绪。
- 每一步失败都要：写日志 + Telegram 推送失败告警（让用户"跑挂了能知道"）。
- 日志按日期落到 `logs/`。

### ml/report.py
- 输入：`predict.py` 产出的 JSON。
- 输出：Markdown，含：日期/SPY 收盘、是否信号日（醒目标注）、底部概率、feature importance Top-N 与当前取值、数据新鲜度、模型可靠性提示。
- **非信号日明确标注"模型未在此场景训练，仅供参考"**（沿用 predict.py 的口径）。

### Telegram 推送
- 前置（用户本人操作一次）：`@BotFather` `/newbot` 拿 token；给 bot 发消息后 `getUpdates` 拿 chat id。
- token/chat id 放 `.env`，不进 git。
- `curl -s -X POST .../sendMessage -d chat_id=... --data-urlencode text=...`。
- 用户 Mac mini 网络干净、无需代理；若日后受限，复用 `.env` 的代理变量即可。

### launchd plist
- 路径：`~/Library/LaunchAgents/com.quant.daily.plist`。
- `StartCalendarInterval`：`Hour=8 Minute=0`（按 Mac mini 系统时区，即北京时间）。
- `StandardOutPath` / `StandardErrorPath` 指向日志文件。
- `RunAtLoad=false`（避免装载即跑）。
- 装载：`launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.quant.daily.plist`（或旧式 `launchctl load`）。

## 六、Mac mini 部署步骤（实施时执行，本轮不做）

1. 安装 Python 3 + git；`git clone` 仓库。
2. `python3 -m venv .venv && source .venv/bin/activate`
3. `pip install -r requirements.txt`（含 scikit-learn / scipy / xgboost）。
4. 确认 `models/` 与 `data/` 已随 git 带来；不齐则首次手动 `fetch`。
5. 创建 `.env`，填 Telegram token / chat id。
6. 手动跑一次 `bash scripts/run_daily.sh` 验证全链路 + 确认收到 Telegram。
7. 放置并装载 `.plist`，确认 `launchctl list | grep quant` 在列。

## 七、风险与兜底

| 风险 | 兜底 |
| --- | --- |
| 唤醒后网络未就绪，fetch 失败 | 脚本内网络探测 + 重试；失败发 Telegram 告警 |
| Mac mini 关机错过 08:00 | launchd 不补关机错过；可考虑下午加一个补跑调度点（待定） |
| 数据源延迟，特征被 ffill 陈旧值填充 | 报告内展示数据新鲜度，用户可识别 |
| 模型为弱信号被误当交易指令 | 报告/推送统一标注"研究观察用，非投资建议"；非信号日额外提示 |
| Telegram token 泄漏 | 仅存 `.env`，`.gitignore` 已忽略 `.env` |

## 八、待用户确认 / 实施前需补充

- Telegram bot token 与 chat id（用户本人获取后填 `.env`）。
- 是否需要"下午补跑调度点"以覆盖偶发关机/早晨断网（默认先只设 08:00 单点）。
- 报告是否需要随时间累积 track record（预测 vs 实际），还是先单日快照（建议先单日，后续加历史回看）。
