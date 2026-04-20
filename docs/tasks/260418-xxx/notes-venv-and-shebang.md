# 知识点梳理：venv 激活机制与脚本免 activate 运行

## 1. 为什么每次开新终端都要重新 activate？

`source .venv/bin/activate` 做的事情很简单：

```
# activate 脚本的核心逻辑（简化版）
export PATH="/path/to/project/.venv/bin:$PATH"
export VIRTUAL_ENV="/path/to/project/.venv"
```

它只是临时修改了当前 shell 的 `PATH` 环境变量，让 `python` 命令优先找到 `.venv/bin/python` 而不是系统的 `/usr/bin/python3`。

**这个修改只在当前 shell 会话中生效。** 关掉终端、开新终端，PATH 就恢复原样了。这是 Linux shell 的基本机制——子进程不能修改父进程的环境变量。

## 2. 不 activate 也能用 venv 的三种方式

### 方式一：直接写全路径（最简单）

```bash
.venv/bin/python scripts/show_chart.py
```

不需要 activate，因为你直接告诉系统"用这个 Python"。`.venv/bin/python` 启动时会自动识别自己所在的 venv 目录，加载 venv 里的包。

### 方式二：写一个 shell 包装脚本

就是我们的 `show_chart.sh` 的做法：

```bash
#!/usr/bin/env bash
cd "$(dirname "$0")"
exec .venv/bin/python scripts/show_chart.py "$@"
```

- `cd "$(dirname "$0")"` — 切到脚本自身所在的目录（项目根目录），保证相对路径 `.venv/bin/python` 能找到
- `exec` — 用 Python 进程替换当前 shell 进程，不会多出一个无用的 shell 进程
- `"$@"` — 把所有命令行参数原样传递给 Python 脚本

### 方式三：shebang 行（有限制）

Python 脚本第一行写 `#!/path/to/.venv/bin/python`，然后 `chmod +x` 后直接 `./script.py` 运行。

**限制：shebang 必须写绝对路径**，不能写相对路径（如 `../../.venv/bin/python`），这是 Linux 内核的限制。所以如果项目目录可能移动，shebang 就不靠谱了。这就是为什么我们选择了 shell 包装脚本的方案。

## 3. `source` 和直接执行的区别

```bash
source .venv/bin/activate    # 在「当前 shell」里执行 activate 脚本
.venv/bin/activate           # 这样不行！会在子 shell 里执行，改完 PATH 子 shell 就退出了
```

`source`（或等价的 `.`）的作用是在当前 shell 进程中执行脚本，而不是启动一个子进程。只有这样，`export PATH=...` 才能影响到你当前的终端。

## 4. `$@` 是什么？

在 shell 脚本里，`$@` 代表传给脚本的所有参数。加双引号 `"$@"` 后，每个参数会被保持为独立的词（即使参数里有空格也不会被拆开）。

```bash
# 用户运行：./show_chart.sh --env bear
# 脚本里 "$@" 展开为：--env bear
# 最终执行：.venv/bin/python scripts/show_chart.py --env bear
```

## 5. `exec` 是什么？

`exec` 命令用新进程替换当前进程，而不是创建子进程。

```bash
# 不用 exec：shell 进程还在，等 python 退出后才结束 → 浪费一个进程
bash → python

# 用 exec：shell 进程直接变成 python 进程 → 更干净
python（替代了 bash）
```

对用户来说没有可感知的区别，但 `exec` 更高效。

## 6. `$(dirname "$0")` 是什么？

- `$0` — 当前脚本的路径（用户怎么调用的就是什么，可能是 `./show_chart.sh` 或 `/full/path/show_chart.sh`）
- `dirname` — 取路径的目录部分（去掉文件名）
- `$(...)` — 命令替换，把 `dirname "$0"` 的输出嵌入到外层命令中

所以 `cd "$(dirname "$0")"` 的意思是：切到脚本自身所在的目录。这样无论用户从哪个目录运行 `./path/to/show_chart.sh`，脚本内部的相对路径（`.venv/bin/python`）都能正确找到。
