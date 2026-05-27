# SOP：上海服务器通过新加坡 SOCKS5 代理访问 Yahoo Finance

## 背景

上海服务器当前出口 IP 是中国大陆 IP，访问 Yahoo Finance 相关接口可能被拦截或限流。新加坡 ECS 已经部署 SOCKS5 代理，上海服务器可以只在抓取 Yahoo Finance 数据时使用该代理，让请求从新加坡出口出去。

## 当前代理信息

| 项目 | 值 |
|------|----|
| 新加坡 ECS 公网 IP | `47.82.223.112` |
| SOCKS5 端口 | `11080` |
| 用户名 | `sgproxy` |
| 密码 | `qNRZBMpYQCyHRj90LLqeVrWz` |
| 推荐协议 | `socks5h` |
| 上海服务器 IP 白名单 | `210.13.96.227/32` |

完整代理串：

```bash
socks5h://sgproxy:qNRZBMpYQCyHRj90LLqeVrWz@47.82.223.112:11080
```

> 必须使用 `socks5h://`，不要使用 `socks5://`。`socks5h` 会让 DNS 解析也走新加坡代理，避免本地 DNS 解析导致访问异常。

## 前置条件

在执行上海服务器侧测试前，需要确认阿里云新加坡 ECS 的安全组已经放行：

| 字段 | 值 |
|------|----|
| 方向 | 入方向 |
| 协议 | TCP |
| 端口 | `11080` |
| 授权对象 | `210.13.96.227/32` |
| 描述 | `socks5-from-shanghai` |

> 如果是在传统 ECS 安全组页面，端口范围可能显示为 `11080/11080`；如果是在“添加防火墙规则”页面，端口范围通常只填 `11080`。以页面校验通过为准。

新加坡 ECS 本机防火墙已经限制只允许 `210.13.96.227` 访问 `11080`，但如果阿里云安全组没有放行，上海服务器仍然连不上。

## Part 1：在上海服务器上验证代理连通性

> 以下命令都在上海服务器上执行。

### Step 1：设置代理变量

```bash
SG_PROXY="socks5h://sgproxy:qNRZBMpYQCyHRj90LLqeVrWz@47.82.223.112:11080"
```

### Step 2：确认出口 IP 已变成新加坡

```bash
curl -s -x "$SG_PROXY" https://ipinfo.io/json
```

预期结果里应包含：

```json
"ip": "47.82.223.112",
"country": "SG"
```

如果这里超时，优先检查阿里云安全组是否放行了 `210.13.96.227/32` 到 TCP `11080`。

### Step 3：测试 Yahoo Finance API

优先测试 `query2.finance.yahoo.com`：

```bash
curl -s \
  -A "Mozilla/5.0" \
  -x "$SG_PROXY" \
  "https://query2.finance.yahoo.com/v8/finance/chart/SPY?range=1d&interval=1d" | head -c 500
```

预期返回类似：

```json
{"chart":{"result":[{"meta":{"currency":"USD","symbol":"SPY"
```

注意：`query1.finance.yahoo.com` 当前可能返回 `429`，建议程序优先使用 `query2.finance.yahoo.com`。

## Part 2：临时让某个 Python 脚本走新加坡出口

推荐使用命令行环境变量，只影响这一次命令，不污染系统全局环境。

```bash
SG_PROXY="socks5h://sgproxy:qNRZBMpYQCyHRj90LLqeVrWz@47.82.223.112:11080"

HTTPS_PROXY="$SG_PROXY" \
HTTP_PROXY="$SG_PROXY" \
python fetch_spy_for_mma.py
```

如果脚本使用 `requests`、`yfinance`、`curl_cffi` 等常见 HTTP 客户端，通常会自动读取 `HTTP_PROXY` 和 `HTTPS_PROXY`。

## Part 3：在 Python 代码中显式配置代理

如果只希望某段请求走代理，可以在代码里显式传入代理配置。

### requests 示例

```python
import requests

proxy = "socks5h://sgproxy:qNRZBMpYQCyHRj90LLqeVrWz@47.82.223.112:11080"
proxies = {
    "http": proxy,
    "https": proxy,
}

resp = requests.get(
    "https://query2.finance.yahoo.com/v8/finance/chart/SPY?range=1d&interval=1d",
    headers={"User-Agent": "Mozilla/5.0"},
    proxies=proxies,
    timeout=30,
)
print(resp.status_code)
print(resp.text[:500])
```

如果 `requests` 报缺少 SOCKS 支持，需要安装：

```bash
pip install "requests[socks]"
```

### 通过环境变量写入 Python

```python
import os

proxy = "socks5h://sgproxy:qNRZBMpYQCyHRj90LLqeVrWz@47.82.223.112:11080"
os.environ["HTTP_PROXY"] = proxy
os.environ["HTTPS_PROXY"] = proxy
```

这段代码需要放在发起 Yahoo Finance 请求之前。

## Part 4：后台任务或 cron 使用方式

如果脚本通过 cron 执行，不要依赖交互式 shell 里的变量，需要在 cron 命令里直接写明代理变量。

示例：

```cron
*/10 * * * * HTTP_PROXY="socks5h://sgproxy:qNRZBMpYQCyHRj90LLqeVrWz@47.82.223.112:11080" HTTPS_PROXY="socks5h://sgproxy:qNRZBMpYQCyHRj90LLqeVrWz@47.82.223.112:11080" /usr/bin/python3 /path/to/fetch_spy_for_mma.py >> /var/log/fetch_spy_for_mma.log 2>&1
```

如果使用 systemd timer 或 systemd service，可以在 service 里加：

```ini
[Service]
Environment="HTTP_PROXY=socks5h://sgproxy:qNRZBMpYQCyHRj90LLqeVrWz@47.82.223.112:11080"
Environment="HTTPS_PROXY=socks5h://sgproxy:qNRZBMpYQCyHRj90LLqeVrWz@47.82.223.112:11080"
```

## Part 5：故障排查

### 连接超时

现象：

```text
curl: (28) Connection timed out
```

常见原因：

- 阿里云安全组没有放行 TCP `11080`
- 授权对象不是 `210.13.96.227/32`
- 上海服务器出口 IP 已变化，不再是 `210.13.96.227`
- 新加坡 ECS 上 `microsocks` 服务未运行

上海服务器上确认自身公网 IP：

```bash
curl -s https://ipinfo.io/ip
```

如果不是 `210.13.96.227`，需要更新新加坡 ECS 的阿里云安全组和本机防火墙白名单。

### 认证失败

现象可能是：

```text
curl: (97) No authentication method was acceptable
```

或请求一直失败。

检查代理串是否完全一致：

```bash
socks5h://sgproxy:qNRZBMpYQCyHRj90LLqeVrWz@47.82.223.112:11080
```

### 出口 IP 不是新加坡

如果 `ipinfo.io` 看到的不是 `47.82.223.112` 或 `country` 不是 `SG`，通常是代理没有生效。

检查点：

- curl 是否带了 `-x "$SG_PROXY"`
- Python 是否设置了 `HTTP_PROXY` 和 `HTTPS_PROXY`
- 协议是否是 `socks5h://`

### Yahoo 返回 429

`429` 表示 Yahoo 侧限流或风控，不代表代理一定坏了。

处理建议：

- 优先使用 `https://query2.finance.yahoo.com`
- 加 `User-Agent: Mozilla/5.0`
- 降低请求频率
- 增加缓存，避免重复请求同一标的和同一时间范围
- 先用 `ipinfo.io` 确认出口确实是新加坡，再排查 Yahoo 侧问题

## Part 6：回滚方式

如果临时不想让脚本走代理，直接不设置 `HTTP_PROXY` 和 `HTTPS_PROXY` 即可。

对于单次命令，改回：

```bash
python fetch_spy_for_mma.py
```

对于当前 shell 中已经 export 的变量，可以取消：

```bash
unset HTTP_PROXY HTTPS_PROXY
unset http_proxy https_proxy
```

如果代码里硬编码了代理，需要删除或注释掉对应的 `os.environ` 或 `proxies` 配置。

## 快速命令卡

```bash
SG_PROXY="socks5h://sgproxy:qNRZBMpYQCyHRj90LLqeVrWz@47.82.223.112:11080"

# 看出口 IP
curl -s -x "$SG_PROXY" https://ipinfo.io/json

# 测 Yahoo Finance
curl -s -A "Mozilla/5.0" -x "$SG_PROXY" \
  "https://query2.finance.yahoo.com/v8/finance/chart/SPY?range=1d&interval=1d" | head -c 500

# 跑 Python 脚本
HTTPS_PROXY="$SG_PROXY" HTTP_PROXY="$SG_PROXY" python fetch_spy_for_mma.py
```
