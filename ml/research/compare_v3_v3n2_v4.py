# -*- coding: utf-8 -*-
"""
三版并排对比：v3 / v3_n2 / v4。

对每个版本跑【统计层 WF】+【经济层 A/B 回测】，并排打印：
  - 统计：整体 AUC-ROC(95% CI) / AUC-PR / OOS 样本数 / 单折稳定性
  - 经济：各版自身 A(全 NDay) vs B(模型过滤) 的 Sharpe / 总收益 / 买入数；条件收益与 t 检验
  - 三条验收判据逐版判定

唯一变量：v3_n2 ↔ v4 仅差 czsc 5 列特征（候选与标签相同）；v3 为历史基准（NDay5）。
不改 ACTIVE_VERSION、不导出生产模型。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from ml.eval_walkforward import run_walkforward
from ml.eval_economics import run_economics

VERSIONS_TO_COMPARE = ["v3", "v3_n2", "v4"]


def _fold_stable(fold_aucs):
    """各折 AUC 是否都 > 0.5（无崩塌）。"""
    if not fold_aucs:
        return False
    return all(a > 0.5 for _, a, _ in fold_aucs)


def _verdict(wf, ec):
    """三条判据：① 统计可信 ② 阈值稳健（B 在一大片阈值优于 A）③ 经济价值。"""
    ci_low = wf["auc_ci"][0]
    c1 = (ci_low > 0.5) and _fold_stable(wf["fold_aucs"])

    a_sharpe = ec["engine_A"]["sharpe_ratio"]
    sweep = [s for s in ec["sweep"] if s["n"] > 0 and s["sharpe"] == s["sharpe"]]
    n_better = sum(1 for s in sweep if s["sharpe"] > a_sharpe)
    c2 = len(sweep) > 0 and n_better >= max(3, len(sweep) // 2)

    cond = ec["conditional"]
    c3 = (ec["engine_B_foldinternal"]["sharpe_ratio"] > a_sharpe) and (cond["t_p"] < 0.05)

    return c1, c2, c3, n_better, len(sweep)


def main():
    results = {}
    for v in VERSIONS_TO_COMPARE:
        print("\n" + "#" * 64)
        print(f"#  评估版本 {v}")
        print("#" * 64)
        wf = run_walkforward(version=v, n_folds=4)
        ec = run_economics(version=v)
        results[v] = (wf, ec)

    # ── 统计层并排 ──
    print("\n" + "=" * 76)
    print("  三版对比 · 统计层（Walk-Forward 样本外）")
    print("=" * 76)
    print(f"  {'版本':<8}{'AUC-ROC':>9}{'95% CI':>20}{'AUC-PR':>9}{'OOS n':>8}{'各折稳定':>10}")
    for v in VERSIONS_TO_COMPARE:
        wf = results[v][0]
        ci = wf["auc_ci"]
        stable = "✓" if _fold_stable(wf["fold_aucs"]) else "✗"
        print(f"  {v:<8}{wf['overall_auc']:>9.4f}"
              f"{f'({ci[0]:.3f}, {ci[1]:.3f})':>20}"
              f"{wf['overall_pr']:>9.4f}{len(wf['oos']):>8}{stable:>9}")

    # ── 经济层并排 ──
    print("\n" + "=" * 76)
    print("  三版对比 · 经济层（各版自身 A 全NDay vs B 模型过滤）")
    print("=" * 76)
    print(f"  {'版本':<8}{'A Sharpe':>9}{'Bfold Sh':>10}{'B0.5 Sh':>9}"
          f"{'打-不打20D':>12}{'收益差p':>9}")
    for v in VERSIONS_TO_COMPARE:
        ec = results[v][1]
        cond = ec["conditional"]
        diff = (cond["e_pass"] - cond["e_skip"]) * 100
        print(f"  {v:<8}{ec['engine_A']['sharpe_ratio']:>9.3f}"
              f"{ec['engine_B_foldinternal']['sharpe_ratio']:>10.3f}"
              f"{ec['engine_B_05']['sharpe_ratio']:>9.3f}"
              f"{diff:>+11.2f}%{cond['t_p']:>9.3f}")

    # ── 三条判据 ──
    print("\n" + "=" * 76)
    print("  三版对比 · 验收判据（①统计可信 ②阈值稳健 ③经济价值）")
    print("=" * 76)
    for v in VERSIONS_TO_COMPARE:
        wf, ec = results[v]
        c1, c2, c3, nb, nt = _verdict(wf, ec)
        mark = lambda b: "✅" if b else "❌"
        print(f"  {v:<8} ①{mark(c1)}  ②{mark(c2)}(B>A 的阈值 {nb}/{nt})  ③{mark(c3)}")

    # ── czsc 增量结论 ──
    if "v3_n2" in results and "v4" in results:
        a = results["v3_n2"][0]["overall_auc"]
        b = results["v4"][0]["overall_auc"]
        print("\n" + "-" * 76)
        print(f"  czsc 特征增量（v3_n2 → v4，候选/标签相同，唯一变量=czsc 5 列）：")
        print(f"    AUC-ROC: {a:.4f} → {b:.4f}  (Δ {b - a:+.4f})")
        print("-" * 76)


if __name__ == "__main__":
    main()
