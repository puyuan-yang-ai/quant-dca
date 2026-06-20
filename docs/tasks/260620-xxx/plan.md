# czsc 缠论接入 quant-dca 主方案

> 配套：同目录 `architecture.md`（架构图 + 数据流）。
> 目标：把开源缠论库 [czsc](https://github.com/waditu/czsc) 接入项目，先**可视化**缠论（分型/笔/中枢/买卖点）画到现有交互式图表，确认算对后再把**买卖点信号**接进回测引擎。

## 决策记录（已与用户对齐）

| 项 | 决策 |
| --- | --- |
| 集成深度 | 方案 B：可视化 + 信号接入（缠论买卖点最终参与买卖决策） |
| 标的/级别 | 仅 SPY 日线（当前只有日线数据，不做多级别联立） |
| 缠论元素 | 全画：分型 FX / 笔 BI / 中枢 ZS / 买卖点（中枢用半透明矩形框） |
| 买卖点来源 | czsc **0.9.69 自带**的信号/买卖点体系（阶段 0 实测摸清产出方式），非自己推导 |
| 买卖点使用 | **单独做一个 ChanEntry**；三类买卖点**全用且按类别分桶区分**（代码+可视化都区分一/二/三买卖），便于单独评估各类准确率/召回率 |
| 推进方式 | 先可视化、肉眼确认缠论算得对，再接信号进引擎 |
| **选版** | **0.9.69 纯 Python**（非 1.0 Rust 版）——目标是亲自魔改缠论核心算法，纯 Python 改完即生效、无需 Rust 编译 |
| **集成方式** | **Vendored**：把 0.9.69 核心源码复制进 `src/chan/czsc_vendor/`，随项目一个 git 管理，可自由魔改 |
| **拷贝范围** | 只拷缠论核心（analyze/objects/enum + 必要 utils），裁掉数据连接器/交易器等用不上的部分 |

## 背景：为什么是 czsc 而非解密 .tn6

- 原始诉求是从加密的 `.tn6`（通达信普通加密，8字节 ECB、固定密钥）里拿缠论源码。
- 社区无公开可复现的完整算法+密钥；主流靠 Windows 闭源工具或动态调试，Linux 不可行、且来路指标可能过拟合。
- czsc 是开源（~5350 stars，TuShare 同源团队，2019 起维护至今）、可 `pip install`、活跃迭代的缠论实现，更可靠。

## 为什么选 0.9.69 + Vendored（核心权衡）

- 目标是**亲自按自己理解改造/升级缠论核心算法**，所以选型不是"装个包用"，而是"把源码变成项目可自由修改的一部分"。
- **0.9.69 纯 Python**：分型/笔/中枢核心在 `analyze.py`，改完即生效，无需 Rust 工具链与编译循环；1.0 把核心搬进 Rust，魔改需改 Rust + maturin/PyO3 重编译，迭代慢。
- 数据量小（SPY 日线几千根），用不上 Rust 性能优势。
- **Vendored** 而非 pip：pip 装在 `.venv/site-packages/`，改动会被升级覆盖、不进 git、多机不同步；复制进 `src/chan/czsc_vendor/` 后随项目 git 管理。

## czsc 0.9.69 关键事实

- 用法骨架（0.9.X）：
  ```python
  from czsc import CZSC
  from czsc.objects import RawBar
  from czsc.enum import Freq
  # 把 SPY 日线每行转成 RawBar(symbol,id,dt,freq,open,close,high,low,vol,amount)
  bars = [RawBar(...) for ...]
  c = CZSC(bars)
  c.bi_list   # 笔
  c.fx_list   # 分型
  # 中枢：0.9.X 由 get_signals/信号函数体系或 utils 推导，阶段 0 实测确认
  ```
- ⚠️ **买卖点产出方式以 0.9.69 实测为准**（旧版用 `get_signals` 回调 + `czsc/signals/` 信号函数）。阶段 0 需摸清具体怎么拿到买卖点——这是最大不确定点。
- License 为 NOASSERTION（非标准），仅学习研究用，商用前需自查。

## 分阶段计划

### 阶段 0：取源码 vendored + 跑通（不碰现有业务代码）
- [ ] clone czsc 0.9.69 到**临时目录**（如 `/tmp`），不放进项目
- [ ] 建 `src/chan/czsc_vendor/`，只复制缠论核心必需文件（analyze/objects/enum + 必要 utils），裁掉数据连接器/交易器等
- [ ] 修正 vendored 内部 import 路径（指向 `src.chan.czsc_vendor.*`），补齐缺失依赖（pandas 等项目已有）
- [ ] 写 `scripts/spike_czsc.py`：读 `data/` SPY 日线 → 转 `RawBar` → `CZSC()` → 打印笔/分型/中枢数量
- [ ] 摸清买卖点：确认 0.9.69 怎么产出买卖点（`get_signals` / `czsc/signals/`），记录函数名与输出结构
- **门槛**：核心跑不通 / 买卖点拿不到 → 停下来同步，再决定退路（pip 装 0.9.69 验证逻辑、或自推导买点）

### 阶段 1：可视化（先看对不对）
- [ ] 新增 `src/chan/__init__.py`、`src/chan/viz_adapter.py`：czsc 对象 → 图表 JSON
  - 笔/中枢：转成 lightweight-charts 的 line series 端点
  - 分型/买卖点：转成 markers
- [ ] 扩展 `interactive_chart.show_interactive_chart` 增加可选参数 `chan_data=None`（默认不传 = 行为不变）
- [ ] 在 `_build_html` 主图加缠论 series/markers（参照 breadth 背离连线写法）
- [ ] 在 `scripts/show_chart.py` 加 `--chan` 开关，叠加显示
- **门槛**：肉眼对照 K 线确认分型/笔/中枢位置合理 → 才进阶段 2

### 阶段 2：信号接入回测引擎
- [ ] `src/modules/entry.py` 新增 `ChanEntry`：构造时用 czsc 买卖点预计算 `_buy_dates`，实现 `should_market_buy` / `should_place_limits`（遵循现有 Entry 协议）
- [ ] 可用 `AndEntry`/`OrEntry` 与 VIX/Breadth 等组合
- [ ] 走标准化执行层做信号质量比较（`FixedTiers(drops=())` + `FixedPyramid(market_shares=1)` + `NoTakeProfit()`，按 CLAUDE.md 规则）
- [ ] 用 `scripts/compare_signals.py` 比较缠论买点 vs 现有信号
- **门槛**：缠论信号在回测里有合理表现（不必盈利，但需可解释）

### 阶段 3（可选）：纳入 ML Meta-Labeling
- [ ] 把缠论买卖点作为 ML 的候选信号源，做 meta-labeling 筛选

## 风险与缓解

| 风险 | 缓解 |
| --- | --- |
| vendored 裁剪后内部 import 断裂 | 阶段 0 逐步补文件直到 spike 跑通；裁不干净就先多拷一点 |
| 买卖点产出方式与预期不符 | 阶段 0 摸清；必要时回退"自推导简化买点" |
| 缠论"重画"特性导致历史信号漂移（未来函数风险） | 回测时只用"已完成的笔/中枢"，避免用未完成笔（`last_bi_extend`） |
| 过拟合（呼应 backtest-overfitting-fable） | 缠论信号当候选项之一，不单独神化；用标准化执行层公平比较 |
| 魔改后与上游脱节 | 已接受：vendored 即放弃上游同步，换取自由修改 |

## 依赖与隔离

- 不在 `requirements.txt` 加 `czsc`（走 vendored，源码在 `src/chan/czsc_vendor/`）。
- 若 vendored 依赖额外第三方库（如旧版用到的某些包），按需加入 `requirements.txt`。
- **隔离原则**：项目其它代码只 import `src/chan/`（适配层），绝不直接 import `czsc_vendor` 内部。
