# 缠论三类买卖点 · czsc 函数使用指导

> 面向 vendored 的 `src/chan/czsc_vendor/signals_cxt.py`（来自 czsc v0.9.69 的 `signals/cxt.py`）。
> 已全部在 SPY 8400 根日线上实测可调用、可命中（见 `scripts/spike_czsc.py`）。

## 0. 前置：怎么构造 CZSC 对象

所有买卖点函数的输入都是一个 **CZSC 对象**，它内部已算好 `bi_list`（笔）。

```python
from src.chan.czsc_vendor import CZSC, RawBar, Freq

bars = [RawBar(symbol='SPY', id=i, dt=..., freq=Freq.D,
               open=, high=, low=, close=, vol=, amount=) for ...]

# ⚠️ 必须传大 max_bi_num，否则默认 50 会截断历史笔（只剩最近一段）
c = CZSC(bars, max_bi_num=len(bars))
```

- 笔：`c.bi_list`（List[BI]，时间升序）
- 分型：`c.fx_list`
- 中枢：`from src.chan.czsc_vendor.utils.sig import get_zs_seq; get_zs_seq(c.bi_list)`

## 1. 三类买卖点 · 函数对照表

缠论买卖点是三类，每类有买点和卖点。czsc 用多个版本的信号函数实现，推荐组合如下：

| 类别 | 函数 | 依赖 | 输出 v1 取值 | 备注 |
| --- | --- | --- | --- | --- |
| **一买** | `cxt_first_buy_V221126` | 纯笔 | `一买` / `其他` | 背驰判断（power_price/volume/length） |
| **一卖** | `cxt_first_sell_V221126` | 纯笔 | `一卖` / `其他` | 一买的镜像 |
| **二买/二卖** | `cxt_second_bs_V230320` | 均线缓存（tas） | `二买` / `二卖` / `其他` | 123 笔 + 均线位置判断 |
| **三买** | `cxt_third_buy_V230228` | 纯笔 | `三买` / `其他` | 向上突破笔重叠 + 回踩不破 |
| **三买/三卖** | `cxt_third_bs_V230319` | 中枢（get_zs_seq）+均线 | `三买` / `三卖` / `其他` | 基于中枢的三类点 |

> 说明：czsc 里没有"一个函数返回三类"的设计，而是**每类点一个或多个信号函数**，各自独立调用、各自返回。`cxt_*_bs_*` 这类是"买卖合一"（v1 可能是买也可能是卖）。

## 2. 调用方式（统一范式）

每个函数签名都是 `fn(c: CZSC, **kwargs) -> OrderedDict`。

```python
from src.chan.czsc_vendor.signals_cxt import cxt_first_buy_V221126

sig = cxt_first_buy_V221126(c, di=1)   # di=1 表示从倒数第1笔开始判断
# sig 形如：OrderedDict({'日线_D1B_BUY1': '一买_5笔_任意_0'})
```

### 输入参数（kwargs）

| 参数 | 含义 | 默认 | 适用函数 |
| --- | --- | --- | --- |
| `di` | 从倒数第 di 笔开始识别（实盘判断当下用 1） | 1 | 全部 |
| `ma_type` | 均线类型（SMA/EMA） | SMA | 二买、三买卖（中枢） |
| `timeperiod` | 均线周期 | 21 | 二买、三买卖（中枢） |

### 输出结构（OrderedDict）

- **key**：信号名，形如 `"{freq}_{参数}_{信号类型}"`，例如 `日线_D1B_BUY1`
- **value**：`"{v1}_{v2}_{v3}_{score}"`，用 `_` 分隔
  - `v1`：核心结论 —— **`一买`/`二买`/`三买`/`一卖`/`二卖`/`三卖`/`其他`**
  - `v2`：辅助描述（如 `5笔`、`均线底分`）
  - `v3`：通常 `任意`
  - score：0

**解析示例**：
```python
for k, v in sig.items():
    v1 = v.split('_')[0]
    if v1 not in ('其他', '任意'):
        print(f"命中 {v1}")   # 命中了某类买卖点
```

## 3. 实测结果（SPY 全历史 1993~2026，逐日增量扫描）

| 信号 | 首次出现 | 命中次数（次） |
| --- | --- | --- |
| 一买 | 1998-10-09 | 229 |
| 一卖 | 1993-05-28 | 1329 |
| 二买 | 1993-06-09 | 1903 |
| 二卖 | 1993-05-06 | 973 |
| 三买（纯笔） | 1993-07-21 | 1194 |
| 三买（中枢） | 1993-09-10 | 872 |
| 三卖（中枢） | 1994-04-08 | 280 |

> 注：命中次数是"每个交易日各函数判断一次"的累计，同一段行情会被连续多日重复命中。阶段 2 接信号时需做**去重 / 取笔结束点**处理，不能直接当独立买点。

## 4. 重要注意事项（阶段 2 接信号前必读）

1. **`max_bi_num` 必须传大值**，否则历史笔被截断，早年买卖点全部消失。
2. **买卖点会随笔重画而变动**（缠论固有特性）。回测要防未来函数：判断当下买卖点时，只用"已完成的笔"（避免依赖 `last_bi_extend` 的未完成笔）。
3. **二买、三买（中枢）依赖均线缓存**：vendored 的 `utils/tas.py` 用纯 numpy 实现了 SMA/EMA/MACD（不依赖 TA-Lib），调用买卖点函数前这些函数内部会自动 `update_ma_cache`。
4. **同一类点有多个版本函数**（如三买有 `V230228` 纯笔 / `V230319` 中枢两种口径），结论不完全一致。阶段 2 需选定一套口径，或做组合投票。
5. **高级函数未启用**：多级别共振（`cxt_zhong_shu_gong_zhen`，需 `CzscSignals`/cat 参数）、盘中（`cxt_intraday`）等依赖未 vendored，当前仅日线单级别。

## 5. 这些函数所在文件

`src/chan/czsc_vendor/signals_cxt.py`（共 43 个 `cxt_*` 函数，本文只覆盖三类买卖点核心；其余为笔状态/趋势/形态等辅助信号，按需取用）。
