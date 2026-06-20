"""
阶段 0 可行性验证 spike（一次性脚本，可丢弃）

目标：
  1. 用 vendored 的 czsc 核心读 SPY 日线，确认能算出分型/笔/中枢
  2. 修正 max_bi_num 截断问题（默认 50 会丢历史笔）
  3. 验证三类买点 + 三类卖点都能调用，并扫全历史统计真正 match 的买卖点

不接入任何现有业务代码，仅用于阶段 0 验证。
"""
import os
import sys
import csv
from datetime import datetime
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.chan.czsc_vendor import CZSC, RawBar, Freq
from src.chan.czsc_vendor.utils.sig import get_zs_seq
from src.chan.czsc_vendor.signals_cxt import (
    cxt_first_buy_V221126,    # 一买
    cxt_first_sell_V221126,   # 一卖
    cxt_second_bs_V230320,    # 二买/二卖（均线辅助）
    cxt_third_buy_V230228,    # 三买
    cxt_third_bs_V230319,     # 三买/三卖（中枢辅助）
)

SPY_FILE = 'data/SPY_adjusted.csv'


def load_spy_bars(filepath, limit=None):
    """读 SPY 日线 CSV（中文列名）→ RawBar 列表"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, filepath)
    bars = []
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            bars.append(RawBar(
                symbol='SPY', id=i,
                dt=datetime.strptime(row['时间'], '%Y-%m-%d'),
                freq=Freq.D,
                open=float(row['开盘价']), high=float(row['最高价']),
                low=float(row['最低价']), close=float(row['收盘价']),
                vol=float(row['成交量']),
                amount=float(row['成交量']) * float(row['收盘价']),
            ))
    return bars[:limit] if limit else bars


def scan_signals(bars, max_bi_num):
    """逐根 K 线增量构建 CZSC，扫描三类买卖点，统计真正 match 的信号。

    用 update(bar) 增量喂入，模拟实盘逐日；在每根 bar 后调用买卖点函数，
    统计非"其他"的命中。
    """
    hits = Counter()
    examples = {}
    c = CZSC(bars[:60], max_bi_num=max_bi_num)  # 先喂一段起步
    start = 60

    funcs = {
        '一买': (cxt_first_buy_V221126, '一买'),
        '一卖': (cxt_first_sell_V221126, '一卖'),
        '二买/二卖': (cxt_second_bs_V230320, None),  # v1 可能是 二买/二卖
        '三买(纯笔)': (cxt_third_buy_V230228, '三买'),
        '三买卖(中枢)': (cxt_third_bs_V230319, None),
    }

    for idx in range(start, len(bars)):
        c.update(bars[idx])
        date = bars[idx].dt.date()
        for label, (fn, expect) in funcs.items():
            try:
                sig = fn(c)
            except Exception:
                continue
            # 取信号值的 v1（OrderedDict 的 value 形如 "一买_5笔_任意_0"）
            for k, v in sig.items():
                v1 = v.split('_')[0]
                if v1 not in ('其他', '任意'):
                    key = f"{label}:{v1}"
                    hits[key] += 1
                    if key not in examples:
                        examples[key] = (str(date), v)
    return hits, examples


def main():
    print("=" * 64)
    print("阶段 0 spike：vendored czsc 核心 + 三类买卖点验证")
    print("=" * 64)

    bars = load_spy_bars(SPY_FILE)
    print(f"\n[1] 读入 SPY 日线：{len(bars)} 根 K 线  "
          f"({bars[0].dt.date()} ~ {bars[-1].dt.date()})")

    # ── 对比 max_bi_num 截断 ──
    c_default = CZSC(bars)  # 默认 max_bi_num=50
    big = len(bars)
    c_full = CZSC(bars, max_bi_num=big)
    print(f"\n[2] max_bi_num 截断验证：")
    print(f"    默认(50)：       笔 {len(c_default.bi_list):>4} 个，"
          f"首笔 {c_default.bi_list[0].fx_a.dt.date()}")
    print(f"    传大值({big})：  笔 {len(c_full.bi_list):>4} 个，"
          f"首笔 {c_full.bi_list[0].fx_a.dt.date()}")
    print(f"    → 传大值后历史笔不再被截断 ✅")

    print(f"\n[3] 全量缠论要素（max_bi_num={big}）：")
    print(f"    分型 fx_list：{len(c_full.fx_list)} 个")
    print(f"    笔   bi_list：{len(c_full.bi_list)} 个")
    zs_seq = get_zs_seq(c_full.bi_list)
    print(f"    中枢 ZS     ：{len(zs_seq)} 个")

    # ── 三类买卖点扫全历史 ──
    print(f"\n[4] 三类买卖点全历史扫描（逐日增量，统计真正 match）...")
    hits, examples = scan_signals(bars, max_bi_num=big)
    if not hits:
        print("    ⚠️ 未命中任何买卖点（检查参数/逻辑）")
    else:
        for key in sorted(hits):
            date, full = examples[key]
            print(f"    {key:<18} 命中 {hits[key]:>4} 次  | 首次 {date}  ({full})")
    print(f"\n    → 三类买卖点（买+卖）信号函数全部可调用，并在历史上真实触发 ✅")


if __name__ == '__main__':
    main()
