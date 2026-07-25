# -*- coding: utf-8 -*-
"""
阶段二·p2-feed：给每个下跌用例附上"回抽级别 L"。

把 box_events.json 里每个用例的"最后上拉窗口"喂给阶段一的 MACD 回抽判定（全 11 级别扫），
得到该用例命中的回抽级别列表 L。命中 ≥1 个 → 展开成 (用例 × L) 多行；零命中 → 跳过。

产出：
  data/intraday/samples.json   —— 阶段三 TD 实验的最终输入（每行一个 (下跌用例, 回抽级别 L)）

性能：11 个级别的重采样+MACD 只预计算一次，再对 258 个窗口逐一切片判定。

用法：
  python scripts/build_samples.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import scan_macd_zero_pullback as smz  # noqa: E402

DATA_DIR = REPO_ROOT / "data" / "intraday"
DEA_TOL_FRAC = 0.10


def main():
    events = json.loads((DATA_DIR / "box_events.json").read_text())
    base = smz._load_base("ESF")
    # 预计算 11 个级别（重采样 + MACD），只算一次
    dfs = {lv: smz._resample(base, lv) for lv in smz.LEVELS}

    samples = []
    hit_events = 0
    for e in events:
        start = pd.Timestamp(e["rally_t0"])
        end = pd.Timestamp(e["rally_t1"])
        hit_levels = []
        for lv in smz.LEVELS:
            res = smz._scan_level(dfs[lv], start, end, DEA_TOL_FRAC)
            if res.get("ok"):
                hit_levels.append(lv)
        if not hit_levels:
            continue
        hit_events += 1
        for L in hit_levels:
            row = dict(e)
            row["pullback_level"] = L  # 回抽级别 L（× 系数 → TD 观察级别）
            samples.append(row)

    out = DATA_DIR / "samples.json"
    out.write_text(json.dumps(samples, ensure_ascii=False, indent=2))

    print(f"下跌用例总数: {len(events)}")
    print(f"至少命中 1 个回抽级别的用例: {hit_events}")
    print(f"展开后样本行数 (用例 × 回抽级别): {len(samples)}")
    # 回抽级别分布
    from collections import Counter
    by_pull = Counter(s["pullback_level"] for s in samples)
    print("回抽级别 L 分布:", dict(sorted(by_pull.items())))
    by_box = Counter(s["level"] for s in samples)
    print("箱体级别分布:", dict(sorted(by_box.items())))
    print(f"\n样本表 -> {out}")


if __name__ == "__main__":
    main()
