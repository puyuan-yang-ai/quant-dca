# Linux 服务器双 GitHub 账号配置 SOP

## 1. 目标与适用场景

本 SOP 用于在一台 Linux 服务器上同时使用两个 GitHub 账号，并实现不同项目使用不同账号进行 `clone`、`pull`、`push`。

本方案基于 SSH，多账号切换通过 `~/.ssh/config` 的 `Host` 别名实现。

## 2. 方案概览

- 默认 `github.com` 走工作账号私钥（例如 `id_rsa`）
- `github-personal` 走个人账号私钥（例如 `id_ed25519`）
- 不同项目通过不同 remote URL 绑定到对应账号

示例：

- 工作项目：`git@github.com:<work-org-or-user>/<repo>.git`
- 个人项目：`git@github-personal:<personal-user>/<repo>.git`

## 3. 前置条件

- 服务器系统：Linux
- 已可登录服务器并有当前用户家目录写权限
- 已从旧机器复制 SSH 文件到服务器（本 SOP 采用复制私钥方案）
- 服务器可访问 GitHub（无网络限制）

## 4. 需要复制的文件

将以下文件从旧机器复制到服务器的 `~/.ssh/` 目录：

- 工作账号私钥与公钥（例如 `id_rsa`、`id_rsa.pub`）
- 个人账号私钥与公钥（例如 `id_ed25519`、`id_ed25519.pub`）
- SSH 配置文件 `config`（可先复制后再按下文校准）

> 说明：私钥文件内容本身不是口令。口令（passphrase）是你生成私钥时手动设置的密码。

## 5. 配置 `~/.ssh/config`

编辑服务器上的 `~/.ssh/config`，确保包含以下核心配置：

```sshconfig
# 默认 GitHub（工作号）
Host github.com
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_rsa
    IdentitiesOnly yes

# 个人 GitHub（别名）
Host github-personal
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes

# 可选：兼容历史别名（等价于工作号）
Host github-work
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_rsa
    IdentitiesOnly yes
```

## 6. 修正文件权限（必须执行）

在服务器执行：

```bash
chmod 700 ~/.ssh
chmod 600 ~/.ssh/config
chmod 600 ~/.ssh/id_rsa ~/.ssh/id_ed25519
chmod 644 ~/.ssh/*.pub
```

## 7. 连通性验证（账号级别）

执行：

```bash
ssh -T git@github.com
ssh -T git@github-personal
```

预期结果：

- `git@github.com` 返回工作账号用户名（`Hi <work-username>! ...`）
- `git@github-personal` 返回个人账号用户名（`Hi <personal-username>! ...`）

> 注意：输出里包含 `GitHub does not provide shell access` 是正常现象，不代表失败。

## 8. 项目使用方式（clone / push）

### 8.1 Clone

- 工作项目：

```bash
git clone git@github.com:<work-org-or-user>/<repo>.git
```

- 个人项目：

```bash
git clone git@github-personal:<personal-user>/<repo>.git
```

### 8.2 仓库内设置提交身份（强烈建议）

进入仓库后，按项目类型设置本仓库身份（`--local`）：

```bash
# 个人项目
git config --local user.name "puyuan-yang-ai"
git config --local user.email "yangpuyuan123@gmail.com"

# 工作项目
git config --local user.name "Puyuan-Yang"
git config --local user.email "puyuyang@amd.com"
```

### 8.3 Push 前检查清单

```bash
git remote -v
git config --local --get user.name
git config --local --get user.email
```

如果 remote 使用 `github-personal`，再验证：

```bash
ssh -T git@github-personal
```

确认后再执行：

```bash
git push origin <branch>
```

## 9. 快速验收（5 条命令）

```bash
ssh -T git@github.com
ssh -T git@github-personal
git remote -v
git config --local --get user.name
git config --local --get user.email
```

满足以下条件即验收通过：

- 两个 `ssh -T` 分别命中预期账号
- 当前仓库 remote 指向正确别名（工作号或个人号）
- 仓库 `user.name` / `user.email` 与目标账号一致

## 10. 常见问题与排查

### 问题 1：`Permission denied (publickey)`

排查顺序：

1. 检查 `~/.ssh/config` 的 `Host`、`IdentityFile` 是否正确
2. 检查私钥文件是否存在，且权限是 `600`
3. 执行 `ssh -T git@github-personal` 看命中哪个账号
4. 检查仓库 remote 是否用错（`github.com` vs `github-personal`）

### 问题 2：提交作者邮箱错了

原因：只设置了全局 git 身份，未设置仓库级（local）身份。

修复：

```bash
git config --local user.name "<correct-name>"
git config --local user.email "<correct-email>"
```

### 问题 3：同一台机器多个项目串号

原因：项目 remote URL 与账号身份策略不一致。

建议：

- 工作项目统一使用 `git@github.com:...`
- 个人项目统一使用 `git@github-personal:...`
- 每个仓库都显式设置 `user.name` / `user.email`（local）
