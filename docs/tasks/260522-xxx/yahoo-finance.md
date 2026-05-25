# Yahoo Finance SOCKS5 代理使用说明

## 背景

当前服务器直接访问 Yahoo Finance 可能被封禁、限流或返回异常。可以通过一台可访问 Yahoo Finance 的新加坡 ECS 做 SOCKS5 代理，让请求从该 ECS 的公网 IP 出口访问 Yahoo Finance。

## 连接信息

代理地址：

```bash
socks5h://sgproxy:qNRZBMpYQCyHRj90LLqeVrWz@47.82.223.112:443
```

拆分信息：

| 项目 | 值 |
|------|----|
| 协议 | `socks5h` |
| 代理 IP | `47.82.223.112` |
| 推荐端口 | `443` |
| 备用端口 | `11080` |
| 用户名 | `sgproxy` |
| 密码 | `qNRZBMpYQCyHRj90LLqeVrWz` |

注意：必须使用 `socks5h://`，不要使用 `socks5://`。`socks5h` 会让 DNS 解析也走代理，避免本地 DNS 解析导致 Yahoo Finance 访问异常。

## 测试出口 IP

```bash
PROXY="socks5h://sgproxy:qNRZBMpYQCyHRj90LLqeVrWz@47.82.223.112:443"

curl -s -x "$PROXY" https://ipinfo.io/json
```

正常情况下，返回结果里的 `ip` 应该是：

```text
47.82.223.112
```

## 服务端检查

如果连接 `47.82.223.112:443` 或 `47.82.223.112:11080` 超时，需要在新加坡 ECS 上确认两件事。

### 1. 安全组和防火墙

在阿里云控制台检查这台 ECS 的安全组入方向规则，确认已经放行：

| 项目 | 值 |
|------|----|
| 协议 | TCP |
| 端口 | `443` 和 `11080` |
| 授权对象 | `0.0.0.0/0` |
| 方向 | 入方向 |

如果服务器本机启用了 `ufw`，也需要放行：

```bash
ufw allow 443/tcp
ufw allow 11080/tcp
ufw status
```

### 2. 代理进程

登录新加坡 ECS 后执行：

```bash
ss -tlnp | grep -E ':443|:11080'
```

正常情况下应该能看到 `microsocks` 正在监听 `0.0.0.0:443` 或 `0.0.0.0:11080`。

如果没有输出，说明代理进程没有启动。可以继续检查：

```bash
systemctl status microsocks
```

如果服务未运行，可以尝试启动：

```bash
systemctl restart microsocks
systemctl status microsocks
```

## 测试 Yahoo Finance

建议优先测试 `query2.finance.yahoo.com`：

```bash
curl -s \
  -A "Mozilla/5.0" \
  -x "$PROXY" \
  "https://query2.finance.yahoo.com/v8/finance/chart/SPY?range=1d&interval=1d" | head -c 500
```

正常情况下会返回包含 `chart`、`result`、`symbol` 的 JSON。

## Python 脚本使用方式

如果脚本使用 `requests`、`curl_cffi`、`yfinance` 等常见 HTTP 客户端，可以通过环境变量让本次进程走代理：

```bash
PROXY="socks5h://sgproxy:qNRZBMpYQCyHRj90LLqeVrWz@47.82.223.112:443"

HTTPS_PROXY="$PROXY" \
HTTP_PROXY="$PROXY" \
python your_script.py
```

## yfinance 示例

```bash
PROXY="socks5h://sgproxy:qNRZBMpYQCyHRj90LLqeVrWz@47.82.223.112:443"

HTTPS_PROXY="$PROXY" \
HTTP_PROXY="$PROXY" \
python - <<'PY'
import yfinance as yf

df = yf.Ticker("ES=F").history(period="5d", interval="1d")
print(df.tail())
PY
```

## 注意事项

- 如果连接超时，需要确认代理服务器安全组或防火墙是否允许当前服务器的公网 IP 访问 TCP `443` 或 `11080`。
- 如果 Yahoo 返回 `429`，通常是 Yahoo 侧限流或风控，不一定代表代理不可用。
- 建议先用 `ipinfo.io` 确认出口 IP 已经变成 `47.82.223.112`，再排查 Yahoo Finance 请求本身。
- 不要把代理地址提交到公开代码仓库或公开日志里。
