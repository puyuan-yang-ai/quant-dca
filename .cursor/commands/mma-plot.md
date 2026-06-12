---
description: 从 scenario_evolution.md 提取剧本数据，填入模板生成走势推演图
argument-hint: <scenario_evolution.md 绝对路径>
---

## 参数校验

`$ARGUMENTS` 应为 `scenario_evolution.md` 文件的绝对路径。

如果 `$ARGUMENTS` 为空或未提供，请立即停止执行，并仅回复：

> ⚠️ 缺少必需参数：请提供 `<scenario_evolution.md 的绝对路径>` 后重新触发。

---

## 工作流程

```
Step 1: 读取数据源
   ├─ 读 $ARGUMENTS（scenario_evolution.md）
   ├─ 运行 python scripts/fetch_es_for_mma.py --days 10
   └─ 读 data/es_daily.csv

Step 2: 提取数据 → 填入模板
   ├─ 读模板 .cursor/commands/plot_mma_scenario_template.py
   ├─ 从 scenario 文件提取 7 类数据
   ├─ 替换模板中 DATA START 到 DATA END 之间的内容
   └─ 写出到 scripts/plot_mma_scenario.py

Step 3: 运行 → 展示
   ├─ python scripts/plot_mma_scenario.py --scenario $ARGUMENTS
   ├─ 读取生成的 PNG 并展示
   └─ 报告输出路径
```

---

## Step 1：读取数据源

1. 读取 `$ARGUMENTS` 指向的 scenario_evolution.md **全文**
2. 运行：
   ```bash
   python scripts/fetch_es_for_mma.py --days 10
   ```
3. 读取 `data/es_daily.csv` 获取最新 ES OHLC

---

## Step 2：提取数据 → 填入模板

### 2.1 读取模板

读取 `.cursor/commands/plot_mma_scenario_template.py`，找到 `# ── DATA START ──` 和 `# ── DATA END ──` 之间的区域。

### 2.2 从 scenario 文件提取 7 类数据

逐一提取以下变量。**变量名和格式必须与模板中的占位数据完全一致。**

#### ① REPORT_DATE / REPORT_TYPE

- 从文件标题行 `# MMA 月报剧本推演 — 2026-06-08` 中提取日期 → `"20260608"`
- 含"月报"→ `"Monthly"`，含"周报"→ `"Weekly"`

#### ② SA_* (剧本 A) / SB_* (剧本 B)

从概率最高的 2 个剧本中提取路径 waypoints：

- **SA_LABEL / SB_LABEL**：剧本简称 + 概率，如 `"A: Correction → New ATH → Jul Crest  (45%)"`
- **SA_DATES / SB_DATES**：从时间线代码块中提取转折日期，格式 `"YYYY-MM-DD"`
- **SA_PRICES / SB_PRICES**：对应价格，区间取中值（如 `7500-7550` → `7525`）。**第一个值必须是 es_daily.csv 最新收盘价**
- **SA_KEY_LABELS / SB_KEY_LABELS**：需要标注文字的关键转折点索引→英文标签

#### ③ CRDS

从 "CRD" 相关内容中提取：`(start_date, end_date, label, stars)`

#### ④ SOLAR_LUNAR

从 "Solar-Lunar" 或逐日校验卡中提取：`(date, bias)`，bias 为 `"Low"` / `"High"` / `"H/L"`

#### ⑤ SUPPORTS / RESISTANCES

从"关键支撑"、"关键阻力"中提取价格区间和标签

#### ⑥ KEY_POINTS

已确认的历史关键点（ATH、Panic Low 等）：`(date, price, label, marker, color_key)`
- marker：`"*"` 星标，`"v"` 倒三角，`"^"` 三角
- color_key：`"ATH"` / `"A"` / `"B"`

#### ⑦ ASTRO_LABELS

最多 3 个重要占星事件标注：`(date, y_position, text, color_key)`
- color_key：`"CRD_1"` 蓝 / `"CRD_2"` 金 / `"CRD_3"` 红

#### ⑧ CURRENT_PHASE

从主剧本时间线中判断当前日期所处的阶段，英文描述，如 `"A: Correction Phase (6/05-6/13)"`

### 2.3 填入模板并写出

将提取的数据替换 `# ── DATA START ──` 到 `# ── DATA END ──` 之间的全部内容（保留这两行标记本身），写出到 `scripts/plot_mma_scenario.py`。

**禁止修改 `# ── DATA END ──` 以下的任何内容。**

---

## Step 3：运行并展示

```bash
python scripts/plot_mma_scenario.py --scenario $ARGUMENTS
```

1. 读取生成的 PNG 并展示给用户
2. 报告输出路径：`<scenario 同目录>/{REPORT_DATE}_scenario_chart.png`

---

## 提取规则备忘

- **日期补全**：`6/13-14` → 取第一个日期 `YYYY-06-13`，年份从文件标题获取
- **价格取中值**：`7500-7550` → `7525`
- **概率**：每个剧本末尾 `概率：XX%` 或 `**概率：XX%**`
- **只画前 2 名**：按概率排序，只取最高的 2 个剧本
- **英文标注**：所有图上文字使用英文（matplotlib 不支持中文）
