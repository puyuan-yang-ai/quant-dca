# 阶段 0 验证结论（czsc vendored 可行性）

> 执行分支：`feat/czsc-chan`。验证脚本：`scripts/spike_czsc.py`（一次性，可丢弃）。
> 结论：**阶段 0 全部通过，可进入阶段 1（可视化）。**

## 一、做了什么

1. clone czsc `v0.9.69`（纯 Python）到 `/tmp/czsc_src`。
2. 只拷贝缠论核心文件到 `src/chan/czsc_vendor/`：
   - `analyze.py`（分型/笔核心算法）、`objects.py`（FX/BI/ZS/RawBar 等）、`enum.py`、`envs.py`
   - `utils/corr.py`（objects 依赖的 `single_linear`）
   - `utils/sig.py`（提供 `get_zs_seq` 中枢推导 + `get_sub_elements`/`create_single_signal`）
   - `signals_cxt.py`（缠论买卖点信号函数，由 `signals/cxt.py` 拷来，已裁剪重依赖）
3. 修正全部内部 import 为相对导入；echarts/plotly 画图依赖改惰性导入；裁掉 pandas/CzscSignals/sklearn/tas 等仅高级信号用到的重依赖。
4. 用 `data/SPY_adjusted.csv`（8400 根日线）实测跑通。

## 二、关键结论

| 缠论要素 | 怎么拿到 | 实测结果（SPY 8400 根日线，`max_bi_num=8400`） |
| --- | --- | --- |
| 分型 FX | `CZSC(bars).fx_list` | 2967 个 ✅ |
| 笔 BI | `CZSC(bars, max_bi_num=大值).bi_list` | 667 个 ✅（默认 50 会截断，已修） |
| 中枢 ZS | **不是 CZSC 属性**，用 `utils.sig.get_zs_seq(c.bi_list)` 从笔推导 | 116 个 ✅ |
| 买卖点 | **不是 CZSC 属性**，用 `signals_cxt.py` 的 `cxt_*` 信号函数（返回 OrderedDict） | **三类买+三类卖全部跑通并真实命中** ✅ |

### 三类买卖点验证（全历史逐日扫描，真正 match）

| 信号 | 首次 | 命中次数 |
| --- | --- | --- |
| 一买 / 一卖 | 1998-10-09 / 1993-05-28 | 229 / 1329 |
| 二买 / 二卖 | 1993-06-09 / 1993-05-06 | 1903 / 973 |
| 三买(纯笔) / 三买(中枢) / 三卖(中枢) | 1993-07/09, 1994-04 | 1194 / 872 / 280 |

详见 `buy-sell-points-guide.md`（三类买卖点函数/用法/输入/输出完整指导）。

## 三、必须记住的坑（影响后续魔改）

1. **`max_bi_num=50` 默认值会截断历史笔**（已解决）：必须 `CZSC(bars, max_bi_num=大值)`，否则 8400 根只剩 50 笔（2024 之后）。
2. **中枢、买卖点都不是 CZSC 的直接属性**，是基于 `bi_list` 的二次推导（`get_zs_seq` / `cxt_*` 信号函数）。适配层要把这层封装好。
3. **二买 / 三买(中枢)依赖均线缓存**：原 czsc 用 TA-Lib，本 vendored 用纯 numpy 重写了 `utils/tas.py`（SMA/EMA/MACD），不引入 TA-Lib。
4. **买卖点会随笔重画变动**（缠论固有），回测防未来函数：只用已完成的笔。
5. **命中次数高、会连续重复**：扫全历史每类点命中数百~上千次，阶段 2 需去重/取笔结束点，不能当独立买点。

## 四、依赖变更

新增 3 个轻量纯 Python 依赖（已装入 `.venv`，待写入 `requirements.txt`）：
- `loguru`（objects/analyze 日志）
- `deprecated`（弃用标注）
- `tqdm`（corr.py 进度条）

## 五、vendored 现状文件清单

```
src/chan/czsc_vendor/
├── __init__.py          ← 出口：CZSC/RawBar/Freq/...
├── analyze.py           ← 分型/笔核心（魔改主战场）
├── objects.py           ← FX/BI/ZS/RawBar 数据结构
├── enum.py
├── envs.py
├── signals_cxt.py       ← 买卖点信号函数（三类买卖点核心已可用）
└── utils/
    ├── __init__.py
    ├── corr.py          ← single_linear
    ├── sig.py           ← get_zs_seq（中枢）/ get_sub_elements / create_single_signal
    └── tas.py           ← 纯 numpy 的 SMA/EMA/MACD 缓存（替代 TA-Lib，供二买/三买）
```

## 六、对原 plan 的修订建议

- 阶段 1 可视化适配层需新增"中枢"取数：`get_zs_seq(c.bi_list)`，而非 `c.zs_list`。
- 阶段 1 构造 CZSC 时务必传大 `max_bi_num`，否则历史笔被截断、图上只有最近一段有缠论线。
