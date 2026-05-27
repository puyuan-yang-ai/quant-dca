# SOP：上海服务器通过新加坡 ECS 出海（SOCKS5 跳板）

## 背景

| 项目 | 说明 |
|------|------|
| 上海服务器 | `210.13.96.227`，AMD 机房，出口是中国大陆 IP（AS9929 联通），被 Yahoo Finance 等服务拦截 |
| 新加坡 ECS | 阿里云新加坡节点，出口是新加坡 IP，Yahoo 不拦 |
| 目标 | 在新加坡服务器上跑一个 SOCKS5 代理服务，上海服务器的脚本通过它出海 |
| 认证方式 | 用户名 + 密码（安全，推荐） |

---

## 角色说明

- **新加坡服务器**（简称「SG 机器」）：负责对外发请求，需要在上面安装 SOCKS5 服务。
- **上海服务器**（简称「SH 机器」）：跑 Python 脚本的主机，通过代理访问外网。

---

## Part 1：在新加坡服务器上装 SOCKS5（microsocks）

> **在 SG 机器上操作。** 系统：Ubuntu。

### Step 1：SSH 登录新加坡服务器

```bash
ssh root@<你的新加坡公网IP>
```

> 公网 IP 在阿里云控制台 → ECS → 实例列表里可以看到。

---

### Step 2：安装 microsocks

microsocks 是一个极轻量的 SOCKS5 服务，内存占用约 2MB，适合长期后台运行。

```bash
# 安装编译依赖
apt update && apt install -y git build-essential

# 克隆源码并编译
git clone https://github.com/rofl0r/microsocks.git
cd microsocks
make

# 安装到系统路径
cp microsocks /usr/local/bin/microsocks
```

---

### Step 3：创建专用用户（可选，增强安全）

```bash
# 新建一个没有 shell 权限的系统账号，专门用于运行代理进程
useradd -r -s /usr/sbin/nologin microsocks
```

---

### Step 4：配置 systemd 服务（让 microsocks 开机自启、后台常驻）

**创建服务文件：**

```bash
cat > /etc/systemd/system/microsocks.service << 'EOF'
[Unit]
Description=microsocks SOCKS5 proxy
After=network.target

[Service]
# -p 端口  -u 用户名  -P 密码  -b 监听地址（0.0.0.0 表示所有网卡）
ExecStart=/usr/local/bin/microsocks -p 11080 -u 你的用户名 -P 你的密码 -b 0.0.0.0
Restart=on-failure
User=nobody

[Install]
WantedBy=multi-user.target
EOF
```

> **注意**：把 `你的用户名` 和 `你的密码` 替换成自己设定的字符串，例如 `sgproxy` / `MyP@ss2026`。密码不要含空格。

**启动并设置开机自启：**

```bash
systemctl daemon-reload
systemctl enable microsocks
systemctl start microsocks

# 确认状态是 active (running)
systemctl status microsocks
```

---

### Step 5：开放阿里云安全组端口

> **在阿里云控制台操作，不是 SSH 命令行。**

路径：阿里云控制台 → ECS → 实例详情 → **安全组** → 管理规则 → 添加入方向规则：

| 字段 | 填写 |
|------|------|
| 协议类型 | TCP |
| 端口范围 | `11080/11080` |
| 授权对象 | `210.13.96.227/32`（只允许上海机器，更安全）|
| 描述 | socks5-from-shanghai |

> 如果以后换了上海机器的 IP，记得回来更新这里。

---

### Step 6：在新加坡服务器本地验证代理可用

```bash
# 用 curl 通过代理访问 ipinfo.io，确认出口 IP 是新加坡
curl -s -x "socks5h://你的用户名:你的密码@127.0.0.1:11080" https://ipinfo.io/json
```

预期返回里 `"country": "SG"` 说明代理正常工作。

---

## Part 2：在上海服务器上测试连接

> **在 SH 机器上操作。**

### Step 7：测试从上海通过代理出海

```bash
SG_IP="<新加坡公网IP>"
USER="你的用户名"
PASS="你的密码"

curl -s -x "socks5h://${USER}:${PASS}@${SG_IP}:11080" https://ipinfo.io/json
```

预期：`"country": "SG"`，出口 IP 显示新加坡。

---

### Step 8：在 Python 脚本中使用代理

**方式 A：命令行前缀（最干净，推荐，只影响该次进程）**

```bash
HTTPS_PROXY="socks5h://你的用户名:你的密码@<新加坡IP>:11080" \
HTTP_PROXY="socks5h://你的用户名:你的密码@<新加坡IP>:11080" \
python fetch_spy_for_mma.py
```

**方式 B：在 Python 代码里硬配置（适合固定后台跑）**

```python
import os
proxy = "socks5h://你的用户名:你的密码@<新加坡IP>:11080"
os.environ["HTTPS_PROXY"] = proxy
os.environ["HTTP_PROXY"] = proxy

# 之后正常调用 yfinance / requests 等，流量自动走代理
```

**方式 C：只传给 requests / curl_cffi Session（最精准隔离）**

```python
import requests
proxies = {
    "http":  "socks5h://你的用户名:你的密码@<新加坡IP>:11080",
    "https": "socks5h://你的用户名:你的密码@<新加坡IP>:11080",
}
resp = requests.get("https://query1.finance.yahoo.com/...", proxies=proxies)
```

> `socks5h://` 中的 `h` 表示 DNS 也走代理，避免 DNS 泄漏导致请求被拦截，**必须用 socks5h 不要用 socks5**。

---

## Part 3：日常维护

### 查看代理运行状态

```bash
# 在新加坡服务器执行
systemctl status microsocks
```

### 重启代理

```bash
systemctl restart microsocks
```

### 修改密码

编辑 `/etc/systemd/system/microsocks.service`，改 `-P 新密码`，然后：

```bash
systemctl daemon-reload && systemctl restart microsocks
```

### 查看连接日志

```bash
journalctl -u microsocks -f
```

---

## 快速参考卡

```
新加坡 IP:    <填入>
端口:          11080
用户名:        <填入>
密码:          <填入>
协议:          socks5h

完整代理串:
socks5h://<用户名>:<密码>@<新加坡IP>:11080
```

---

## 常见问题

| 现象 | 原因 | 解决 |
|------|------|------|
| `curl` 连接超时 | 安全组端口没开 | 检查阿里云安全组，确认 11080 对上海 IP 开放 |
| `curl` 返回 407 | 用户名密码错误 | 重新检查 service 文件里的 `-u` / `-P` 参数 |
| 出口 IP 不是新加坡 | 用了 `socks5://` 而不是 `socks5h://` 导致 DNS 泄漏 | 改用 `socks5h://` |
| Yahoo 仍返回 429 | 新加坡 IP 段也被该 Yahoo 节点标记 | 先 `curl ... https://ipinfo.io` 确认出口确实是 SG，再排查 |
| microsocks 重启后失效 | systemd 未 enable | `systemctl enable microsocks` |
