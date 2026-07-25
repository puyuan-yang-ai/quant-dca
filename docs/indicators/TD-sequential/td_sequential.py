# -*- coding: utf-8 -*-
"""
TD Sequential（神奇九转）—— 蓝本 Jason Perl《DeMark Indicators》(2008)。

完整口径与人工校验清单见：docs/indicators/TD-sequential/note.md
本模块以**买入(低)方向**为主（抄底），卖出(高)的 Setup 一并计算（Countdown 取消规则需要它）。

输出均为与输入等长的 per-bar 列表，便于上层（阶段三实验）逐根查询。

⚠️ Countdown 方案A 的 recycle / 取消 / TDST 这几条，各家实现易有出入。
   本实现严格按 Perl 2008，并在关键处标注假设，**务必对照 TradingView 人工校验**。
"""
from dataclasses import dataclass, field
from typing import Dict, List, Sequence

# Setup/Countdown 默认参数（Perl 2008）
SETUP_LOOKBACK = 4      # close vs close[4]
SETUP_LEN = 9
CD_LOOKBACK = 2         # close vs low[2]
CD_LEN = 13
RECYCLE_TR_MULT = 1.618
RECYCLE_SETUP_LEN = 18  # Rule III：setup 延伸到 18 根则 countdown 取消


def _true_highs(highs: Sequence[float], closes: Sequence[float]) -> List[float]:
    """真实高 = max(high, 前一根收盘)。"""
    out = [float(highs[0])]
    for i in range(1, len(highs)):
        out.append(max(highs[i], closes[i - 1]))
    return out


def _true_lows(lows: Sequence[float], closes: Sequence[float]) -> List[float]:
    """真实低 = min(low, 前一根收盘)。"""
    out = [float(lows[0])]
    for i in range(1, len(lows)):
        out.append(min(lows[i], closes[i - 1]))
    return out


def compute_setups(closes: Sequence[float]) -> Dict[str, List[int]]:
    """买/卖 Setup 连续计数（不封顶，便于方案B 的"溢出"读取）。

    买：close < close[4] 连续累加，中断归零。
    卖：close > close[4] 连续累加，中断归零。
    """
    n = len(closes)
    buy = [0] * n
    sell = [0] * n
    for i in range(n):
        if i >= SETUP_LOOKBACK and closes[i] < closes[i - SETUP_LOOKBACK]:
            buy[i] = buy[i - 1] + 1 if i > 0 and buy[i - 1] > 0 else 1
        if i >= SETUP_LOOKBACK and closes[i] > closes[i - SETUP_LOOKBACK]:
            sell[i] = sell[i - 1] + 1 if i > 0 and sell[i - 1] > 0 else 1
    return {"buy": buy, "sell": sell}


@dataclass
class SetupRun:
    """一段连续的买入 Setup 走势（可能延伸到 9 根以上）。"""
    start: int          # 计数=1 的索引
    nine_index: int     # 计数=9 的索引（完成 setup 的那根）
    end: int            # 该连续段的最后一根索引
    length: int         # 段长（连续根数）
    tr: float           # 真实波幅 = 段内 max(真实高) - min(真实低)
    tdst: float         # 买入 TDST 阻力 = 前9根 max(真实高)
    perfected: bool     # 完美结构（第8或9根最低 ≤ 第6、7根最低）


def find_buy_setup_runs(highs, lows, closes, buy_counts) -> List[SetupRun]:
    """从买入 Setup 计数中提取所有"完成段"（计数达到 9 的连续段）。"""
    th = _true_highs(highs, closes)
    tl = _true_lows(lows, closes)
    runs: List[SetupRun] = []
    n = len(buy_counts)
    i = 0
    while i < n:
        if buy_counts[i] == 1:
            j = i
            while j + 1 < n and buy_counts[j + 1] == buy_counts[j] + 1:
                j += 1
            length = buy_counts[j]  # = j - i + 1
            if length >= SETUP_LEN:
                nine = i + SETUP_LEN - 1
                tr = max(th[i:j + 1]) - min(tl[i:j + 1])
                tdst = max(th[i:nine + 1])
                # 完美结构：第8或9根最低 ≤ 第6、7根最低
                b6, b7, b8, b9 = i + 5, i + 6, i + 7, i + 8
                perf = (lows[b8] <= lows[b6] and lows[b8] <= lows[b7]) or \
                       (lows[b9] <= lows[b6] and lows[b9] <= lows[b7])
                runs.append(SetupRun(i, nine, j, length, tr, tdst, perf))
            i = j + 1
        else:
            i += 1
    return runs


def compute_buy_countdown_perl(highs, lows, closes,
                               buy_counts, sell_counts) -> Dict[str, list]:
    """买入 Countdown（方案A，Perl 2008 正统）。

    返回 per-bar：
      cd      : 当前 countdown 计数（0~13）
      status  : ''/'defer'/'complete'/'cancel'/'recycle'（事件标记）
    """
    n = len(closes)
    tl = _true_lows(lows, closes)
    cd = [0] * n
    status = [""] * n

    runs = find_buy_setup_runs(highs, lows, closes, buy_counts)
    nine_at = {r.nine_index: r for r in runs}          # 完成 setup 的根 -> run
    run_end_len = {r.end: r.length for r in runs}       # 段末 -> 段长（判 18 根）
    sell_complete = {i for i in range(n) if sell_counts[i] == SETUP_LEN}

    active = False
    count = 0
    bar8_close = None       # countdown 第8根收盘
    cur_tdst = None         # 当前 countdown 的 TDST 阻力
    cur_tr = None           # 启动当前 countdown 的 setup 的 TR

    def _start(run: SetupRun, i: int):
        """在第9根 i 处尝试启动 countdown。"""
        nonlocal active, count, bar8_close, cur_tdst, cur_tr
        active = True
        count = 0
        bar8_close = None
        cur_tdst = run.tdst
        cur_tr = run.tr
        # 第9根若 close ≤ low[2] 则它即 countdown 第1根
        if i >= CD_LOOKBACK and closes[i] <= lows[i - CD_LOOKBACK]:
            count = 1
            cd[i] = 1

    for i in range(n):
        # —— 1) 取消检查（针对已激活且未完成的 countdown）——
        if active:
            # (1) 反向卖出 Setup 完成
            if i in sell_complete:
                active = False
                count = 0
                status[i] = "cancel"
            # (2) 真实低 高于 TDST 阻力
            elif cur_tdst is not None and tl[i] > cur_tdst:
                active = False
                count = 0
                status[i] = "cancel"

        # —— 2) Rule III：某买入 setup 段延伸到 18 根 → 取消 ——
        if active and run_end_len.get(i, 0) >= RECYCLE_SETUP_LEN:
            active = False
            count = 0
            status[i] = "cancel"

        # —— 3) 新买入 setup 完成（recycle 或 启动）——
        if i in nine_at:
            run = nine_at[i]
            if active:
                # recycle Qualifier I：TR_prior ≤ TR_new < 1.618×TR_prior → 取代
                if cur_tr is not None and cur_tr <= run.tr < RECYCLE_TR_MULT * cur_tr:
                    status[i] = "recycle"
                    _start(run, i)
                # Qualifier II（setup 套 setup，TR_new < TR_prior）：旧的保留，不动
            else:
                _start(run, i)
            continue  # 第9根已在 _start 内处理计数，避免重复

        # —— 4) Countdown 计数（已激活、且非第9根启动那一根）——
        if active and count >= 1 and i >= CD_LOOKBACK and closes[i] <= lows[i - CD_LOOKBACK]:
            prospective = count + 1
            if prospective < CD_LEN:
                count = prospective
                cd[i] = count
                if count == 8:
                    bar8_close = closes[i]
            else:  # 想记为 13：需 13-vs-8 资格
                if bar8_close is not None and lows[i] <= bar8_close:
                    count = CD_LEN
                    cd[i] = CD_LEN
                    status[i] = "complete"
                    active = False  # 完成后本段结束
                else:
                    cd[i] = 12      # 停在 12，递延
                    status[i] = "defer"
        elif active and count >= 1:
            cd[i] = count  # 保持当前计数（非计数根）

    return {"cd": cd, "status": status}


def compute_td(highs: Sequence[float], lows: Sequence[float],
               closes: Sequence[float]) -> Dict[str, list]:
    """一次性计算 TD 全部口径，返回 per-bar 列表字典。

    键：
      buy_setup / sell_setup   : Setup 连续计数（不封顶；方案B 的"低13"= buy_setup 达到 13）
      buy_setup_perfected      : bool，完美结构（仅在完成段的第9根标 True）
      buy_cd / buy_cd_status   : Countdown 方案A（Perl 2008）计数与事件标记
    """
    n = len(closes)
    highs = [float(x) for x in highs]
    lows = [float(x) for x in lows]
    closes = [float(x) for x in closes]

    setups = compute_setups(closes)
    runs = find_buy_setup_runs(highs, lows, closes, setups["buy"])
    perfected = [False] * n
    for r in runs:
        perfected[r.nine_index] = r.perfected

    cd = compute_buy_countdown_perl(highs, lows, closes, setups["buy"], setups["sell"])

    return {
        "buy_setup": setups["buy"],
        "sell_setup": setups["sell"],
        "buy_setup_perfected": perfected,
        "buy_cd": cd["cd"],
        "buy_cd_status": cd["status"],
    }
