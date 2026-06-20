"""
对数脚本：跑真实行情数据，打印三个指标的信号点位，方便与 TradingView 比对。

用途：在 TradingView 上加载对应 .pine 指标后，用本脚本输出的信号日期/数值
和图表逐点核对，确认 Python 版与 Pine 版一致，再决定是否接入量化系统。

用法：
    cd docs/indicators/xxx
    python verify_signals.py                 # 默认 SPY，近 2 年
    python verify_signals.py SMH 2024-01-01  # 指定标的与起始日期
"""
import csv
import importlib.util
import os
import sys

_HERE = os.path.dirname(__file__)


def _load_module(name, rel_path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_HERE, rel_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ind4 = _load_module("ind4_divergence", "ind4_divergence/ind4_divergence.py")
ind5 = _load_module("ind5_obv", "ind5_obv/ind5_obv.py")
ind5v2 = _load_module("ind5_obv_v2", "ind5_obv/ind5_obv_v2.py")
ind1 = _load_module("ind1_radar", "ind1_radar/ind1_radar.py")

# 项目 data 目录（相对本文件 ../../../data）
DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")
)


def load_ohlcv(symbol, start_date=None):
    """读取 {symbol}_adjusted.csv，返回 dict of lists（含成交量）。"""
    path = os.path.join(DATA_DIR, f"{symbol}_adjusted.csv")
    dates, o, h, l, c, v = [], [], [], [], [], []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            d = row["时间"]
            if start_date and d < start_date:
                continue
            dates.append(d)
            o.append(float(row["开盘价"]))
            h.append(float(row["最高价"]))
            l.append(float(row["最低价"]))
            c.append(float(row["收盘价"]))
            v.append(float(row["成交量"]))
    return {"date": dates, "open": o, "high": h, "low": l, "close": c, "volume": v}


def print_signals(title, dates, mask, value_series=None):
    """打印某个 bool 信号序列触发的日期（及可选数值）。"""
    hits = [i for i, m in enumerate(mask) if m]
    print(f"\n  [{title}] 共 {len(hits)} 次")
    for i in hits[-20:]:  # 只打印最近 20 次，避免刷屏
        extra = ""
        if value_series is not None and value_series[i] is not None:
            extra = f"  值={value_series[i]:.2f}"
        print(f"    {dates[i]}{extra}")


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "SPY"
    start = sys.argv[2] if len(sys.argv) > 2 else "2024-01-01"
    data = load_ohlcv(symbol, start)
    dates = data["date"]
    print(f"标的={symbol}  起始={start}  共 {len(dates)} 根 K 线  "
          f"({dates[0]} ~ {dates[-1]})")

    # ---------- 指标④ 三重背离 ----------
    print("\n=== 指标④ 三重背离 + 超卖买点 ===")
    r4 = ind4.compute(data["close"], data["high"], data["low"])
    print_signals("MACD底背", dates, r4["macd_bottom"])
    print_signals("KDJ底背", dates, r4["kdj_bottom"])
    print_signals("RSI底背", dates, r4["rsi_bottom"])
    print_signals("三重底背离共振", dates, r4["triple_bottom"])
    print_signals("MACD顶背", dates, r4["macd_top"])
    print_signals("超卖买点", dates, r4["buy"])
    print_signals("超买卖点", dates, r4["sell"])

    # ---------- 指标⑤ OBV量能 ----------
    print("\n=== 指标⑤ OBV量能潮 + 量价确认 ===")
    r5 = ind5.compute(data["close"], data["volume"])
    print_signals("量价同步QS", dates, r5["qs"])
    print_signals("放量④(250日峰)", dates, r5["fl4"])
    print_signals("放量③(120日峰)", dates, r5["fl3"])

    # ---------- 指标⑤ v2 精简版 ----------
    print("\n=== 指标⑤ v2 精简版（归一化 + 背离 + 天量）===")
    r5v2 = ind5v2.compute(data["close"], data["high"], data["low"], data["volume"])
    print_signals("底背离(看涨)", dates, r5v2["bull_div"])
    print_signals("顶背离(看跌)", dates, r5v2["bear_div"])
    print_signals("天量④(250日)", dates, r5v2["hv4"])
    print_signals("天量③(120日)", dates, r5v2["hv3"])

    # ---------- 指标① 买卖雷达 ----------
    print("\n=== 指标① 买卖雷达 ===")
    r1 = ind1.compute(data["open"], data["high"], data["low"], data["close"])
    print_signals("买点雷达", dates, r1["buy_radar"], r1["rsi7"])
    print_signals("卖点雷达", dates, r1["sell_radar"], r1["rsi6"])


if __name__ == "__main__":
    main()
