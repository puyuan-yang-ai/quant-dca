---
description: 将 PDF 文件转换为同目录同名的 Markdown 文件（使用 markitdown）
argument-hint: <PDF 绝对路径，支持多个路径以空格分隔>
---

## 参数校验（最高优先级，必须先执行）

`$ARGUMENTS` 应为一个或多个 PDF 文件的绝对路径，以空格分隔。

如果 `$ARGUMENTS` 为空或未提供，请立即停止执行，并仅回复以下提示，不要执行任何后续步骤：

> ⚠️ 缺少必需参数：请提供 `<PDF 文件的绝对路径>` 后重新触发。示例：`/pdf2md /home/puyuyang/Projects/.../file.pdf`

## 任务

在终端中运行以下命令，将 `$ARGUMENTS` 中的每个 PDF 转换为同目录同名的 `.md` 文件：

```bash
/home/puyuyang/Projects/quant-dca/.venv/bin/python \
  /home/puyuyang/Projects/quant-dca/.cursor/commands/pdf2md.py \
  $ARGUMENTS
```

转换完成后，告知用户每个 PDF 对应的输出 `.md` 文件路径。如有错误，显示错误信息。
