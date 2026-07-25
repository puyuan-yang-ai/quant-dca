# -*- coding: utf-8 -*-
"""
阶段三：TD 九转抄底验证。

链路：样本(下跌用例 + 回抽级别 L) → TD级别 = L×系数 → 在主跌浪里找 TD 买入信号(低7/8/9)
     → 看信号距底部多少根 K 线 → 命中(≤N 根) 判定。

本文件先做 **3a：单配置 sanity**（系数=3、信号=第1次低9、N=3），
打印"低9 距底部根数"的分布与命中率，确认引擎与方向，再扩展到 3b 的参数网格。

用法：
  python scripts/td_bottom_experiment.py            # 3a 单配置 sanity
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.indicators.td_sequential import compute_td  # noqa: E402

DATA_DIR = REPO_ROOT / "data" / "intraday"
BASE_MINUTES = 5

# —— 3a 单配置 ——
COEF = 3.0
SIGNAL_COUNT = 9     # 低9
OCCURRENCE = 1       # 第 1 次
N = 3                # 命中阈值：信号距底部 ≤ N 根 TD K 线

_TD_CACHE: dict[int, pd.DataFrame] = {}


def _td_df(base: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """重采样到 minutes 级别并附 TD 计数（缓存）。"""
    if minutes in _TD_CACHE:
        return _TD_CACHE[minutes]
    if minutes == BASE_MINUTES:
        df = base.copy()
    else:
        df = base.resample(f"{minutes}min", label="left", closed="left").agg({
            "开盘价": "first", "最高价": "max", "最低价": "min",
            "收盘价": "last", "成交量": "sum",
        }).dropna(subset=["收盘价"])
    df = df.reset_index()
    td = compute_td(df["最高价"].tolist(), df["最低价"].tolist(), df["收盘价"].tolist())
    for k, v in td.items():
        df[k] = v
    df["run_perfected"] = _run_perfected(df["buy_setup"].tolist(), df["buy_setup_perfected"].tolist())
    _TD_CACHE[minutes] = df
    return df


def _run_perfected(bs, perf):
    """把"完美"标志从九转的第9根扩散到整段连续 setup（供完美结构过滤）。"""
    n = len(bs)
    out = [False] * n
    i = 0
    while i < n:
        if bs[i] == 1:
            j = i
            while j + 1 < n and bs[j + 1] == bs[j] + 1:
                j += 1
            rp = any(perf[i:j + 1])
            for t in range(i, j + 1):
                out[t] = rp
            i = j + 1
        else:
            i += 1
    return out


def _td_level(L: int, coef: float) -> int:
    m = int(round(L * coef))
    return max(BASE_MINUTES, int(round(m / 5) * 5))  # 取最近的 5 的倍数


def analyze(base, sample, coef, count_thr, occurrence, N):
    """返回 dict：{td_level, has_signal, dist, hit, n_signals} 或 None(无法评估)。"""
    L = sample["pullback_level"]
    td_min = _td_level(L, coef)
    df = _td_df(base, td_min)

    t_high = pd.Timestamp(sample["rally_t1"])
    t_bottom = pd.Timestamp(sample["bottom_t"])
    # 主跌浪窗口：下跌起点 → 底部（+1天缓冲，容许信号略晚于底）
    win = df[(df["时间"] >= t_high) & (df["时间"] <= t_bottom + pd.Timedelta(days=1))]
    if len(win) < 2:
        return {"td_level": td_min, "evaluable": False}

    # 底部 bar（TD 级别上窗口内最低 low）
    bottom_pos = win["最低价"].idxmin()
    # 低N 信号：setup 计数恰好 == count_thr 的根
    sig_rows = win[win["buy_setup"] == count_thr]
    n_sig = len(sig_rows)
    if n_sig < occurrence:
        return {"td_level": td_min, "evaluable": True, "has_signal": False, "n_signals": n_sig}

    sig_pos = sig_rows.index[occurrence - 1]      # 第 occurrence 次
    dist = int(sig_pos - bottom_pos)              # 正=信号在底之后；负=之前
    hit = abs(dist) <= N
    return {"td_level": td_min, "evaluable": True, "has_signal": True,
            "n_signals": n_sig, "dist": dist, "hit": hit}


# ===================== 3b：跌幅过滤 + 三拨切分 + 消融 + 基准 =====================
GRID_COEF = [2, 2.5, 3, 3.5, 4]
GRID_N = [1, 2, 3, 5, 8]
DROP_THRESHOLDS = [0.005, 0.01, 0.015, 0.02]  # 跌幅过滤门槛
MIN_FIRED = 8                                  # 开发集最少触发数

# 信号定义（消融维度）：setup 低7/8/9×第几次、完美低9、CountdownA、CountdownB
def _signaldefs():
    defs = []
    for k in (7, 8, 9):
        for occ in (1, 2, 3):
            defs.append({"key": f"低{k}#{occ}", "mode": "setup", "count": k, "occ": occ, "perf": False})
    defs.append({"key": "低9#1完美", "mode": "setup", "count": 9, "occ": 1, "perf": True})
    defs.append({"key": "CountdownA", "mode": "cd_a", "occ": 1})
    defs.append({"key": "CountdownB溢出13", "mode": "cd_b", "occ": 1})
    return defs


SIGNALDEFS = _signaldefs()


def _drop_pct(s):
    return (s["rally_p1"] - s["bottom_p"]) / s["rally_p1"] if s.get("bottom_p") else 0.0


def signal_dist(base, sample, coef, sdef):
    """按信号定义 sdef 返回 (dist, declen)。"""
    df = _td_df(base, _td_level(sample["pullback_level"], coef))
    t_high = pd.Timestamp(sample["rally_t1"])
    t_bottom = pd.Timestamp(sample["bottom_t"])
    win = df[(df["时间"] >= t_high) & (df["时间"] <= t_bottom + pd.Timedelta(days=1))]
    if len(win) < 2:
        return None, 0
    bottom_pos = win["最低价"].idxmin()
    mode = sdef["mode"]
    if mode == "setup":
        sig = win[win["buy_setup"] == sdef["count"]]
        if sdef.get("perf"):
            sig = sig[sig["run_perfected"]]
    elif mode == "cd_a":
        sig = win[win["buy_cd_status"] == "complete"]
    else:  # cd_b：Setup 溢出到 13
        sig = win[win["buy_setup"] == 13]
    occ = sdef["occ"]
    if len(sig) < occ:
        return None, len(win)
    return int(sig.index[occ - 1] - bottom_pos), len(win)


def _metrics(idxs, dist_map, sk, coef, N):
    fired = hit = 0
    base_sum = 0.0
    for i in idxs:
        dist, declen = dist_map[(i, coef, sk)]
        if declen >= 1:
            base_sum += min(2 * N + 1, declen) / declen
        if dist is not None:
            fired += 1
            if abs(dist) <= N:
                hit += 1
    total = len(idxs)
    prec = hit / fired if fired else 0.0
    baseline = base_sum / total if total else 0.0
    return dict(fired=fired, hit=hit, prec=prec, baseline=baseline, lift=prec - baseline)


def _split3(idxs, samples):
    """按时间 60/20/20 三拨切分。"""
    order = sorted(idxs, key=lambda i: samples[i]["rally_t1"])
    n = len(order)
    a, b = int(n * 0.6), int(n * 0.8)
    return order[:a], order[a:b], order[b:]


def run_grid(base, samples):
    # 预计算所有 (样本, coef, 信号定义) 的 dist
    dist_map = {}
    for i, s in enumerate(samples):
        for coef in GRID_COEF:
            for sdef in SIGNALDEFS:
                dist_map[(i, coef, sdef["key"])] = signal_dist(base, s, coef, sdef)

    print("=" * 104)
    print("  阶段3b：跌幅过滤 × 信号消融 × 系数 × N  | 三拨 60/20/20（训练选/验证挑/测试封存）")
    print("  指标 lift = 精度 − 随机基准；按 训练 lift 选 top，再用 验证 lift 定最优，最后看 测试")
    print("=" * 104)

    for thr in DROP_THRESHOLDS:
        kept = [i for i in range(len(samples)) if _drop_pct(samples[i]) >= thr]
        train, val, test = _split3(kept, samples)
        # 枚举配置
        configs = []
        for sdef in SIGNALDEFS:
            for coef in GRID_COEF:
                for N in GRID_N:
                    tr = _metrics(train, dist_map, sdef["key"], coef, N)
                    if tr["fired"] >= MIN_FIRED:
                        configs.append((sdef, coef, N, tr))
        print(f"\n── 跌幅≥{thr*100:.1f}%  保留{len(kept)} (训{len(train)}/验{len(val)}/测{len(test)})  "
              f"合格配置 {len(configs)} ──")
        if not configs:
            print("    无满足最小触发数的配置（样本太少）")
            continue
        configs.sort(key=lambda c: c[3]["lift"], reverse=True)
        # 取训练 top10，按验证 lift 选最优
        top = configs[:10]
        top.sort(key=lambda c: _metrics(val, dist_map, c[0]["key"], c[1], c[2])["lift"], reverse=True)
        sdef, coef, N, tr = top[0]
        va = _metrics(val, dist_map, sdef["key"], coef, N)
        te = _metrics(test, dist_map, sdef["key"], coef, N)
        print(f"    最优: 信号={sdef['key']} 系数={coef} N={N}")
        print(f"      训练 lift {tr['lift']:+.1%} (P{tr['prec']:.0%}/基准{tr['baseline']:.0%}, 触发{tr['fired']})")
        print(f"      验证 lift {va['lift']:+.1%} (P{va['prec']:.0%}/基准{va['baseline']:.0%}, 触发{va['fired']})")
        print(f"      测试 lift {te['lift']:+.1%} (P{te['prec']:.0%}/基准{te['baseline']:.0%}, 触发{te['fired']})")

    # 消融：在 跌幅≥1% 全量(不分拨)上，看每个信号家族能达到的最佳 lift（仅供观察，非严格)
    print("\n" + "=" * 104)
    print("  消融观察（跌幅≥1%，全量，每个信号定义在 coef×N 上的最佳 lift）")
    print("=" * 104)
    kept = [i for i in range(len(samples)) if _drop_pct(samples[i]) >= 0.01]
    for sdef in SIGNALDEFS:
        best = None
        for coef in GRID_COEF:
            for N in GRID_N:
                m = _metrics(kept, dist_map, sdef["key"], coef, N)
                if m["fired"] >= MIN_FIRED and (best is None or m["lift"] > best[2]["lift"]):
                    best = (coef, N, m)
        if best:
            coef, N, m = best
            print(f"  {sdef['key']:>14}: 最佳 lift {m['lift']:+.1%}  (系数{coef} N{N} 触发{m['fired']} P{m['prec']:.0%}/基准{m['baseline']:.0%})")
        else:
            print(f"  {sdef['key']:>14}: 触发不足")
    print("\n  注：60天数据、测试样本极少，结论仅作方向参考。")


def main():
    parser = argparse.ArgumentParser(description="阶段三 TD 抄底验证")
    parser.add_argument("--mode", choices=["sanity", "grid"], default="sanity")
    args = parser.parse_args()

    base = pd.read_csv(DATA_DIR / f"ESF_{BASE_MINUTES}m.csv", parse_dates=["时间"]).set_index("时间")
    samples = json.loads((DATA_DIR / "samples.json").read_text())

    if args.mode == "grid":
        run_grid(base, samples)
        return

    res = [analyze(base, s, COEF, SIGNAL_COUNT, OCCURRENCE, N) for s in samples]
    evaluable = [r for r in res if r.get("evaluable")]
    with_sig = [r for r in evaluable if r.get("has_signal")]
    dists = [r["dist"] for r in with_sig]
    hits = [r for r in with_sig if r["hit"]]

    print("=" * 64)
    print(f"  阶段3a 单配置 sanity  |  系数={COEF}  信号=第{OCCURRENCE}次低{SIGNAL_COUNT}  N={N}")
    print("=" * 64)
    print(f"  样本行数: {len(samples)}")
    print(f"  可评估(TD窗口≥2根): {len(evaluable)}")
    print(f"  其中出现 低{SIGNAL_COUNT} 信号的: {len(with_sig)}")
    print(f"  命中(|信号-底| ≤ {N} 根): {len(hits)}")
    if with_sig:
        print(f"  命中率(在有信号样本中): {len(hits)/len(with_sig):.1%}")
    if dists:
        import statistics as st
        absd = [abs(d) for d in dists]
        print(f"\n  距底部根数 |dist| 统计: min={min(absd)} 中位数={st.median(absd):.1f} "
              f"均值={st.mean(absd):.1f} max={max(absd)}")
        # 简单直方图
        from collections import Counter
        bins = Counter(min(abs(d), 10) for d in dists)  # ≥10 归一档
        print("  |dist| 分布(0..9, 10+):")
        for b in range(0, 11):
            label = f"{b}" if b < 10 else "10+"
            print(f"    {label:>3}: {'#'*bins.get(b,0)} ({bins.get(b,0)})")
        # 信号相对底部的方向
        before = sum(1 for d in dists if d < 0)
        at = sum(1 for d in dists if d == 0)
        after = sum(1 for d in dists if d > 0)
        print(f"\n  信号位置：底之前 {before}  正好在底 {at}  底之后 {after}")


if __name__ == "__main__":
    main()
