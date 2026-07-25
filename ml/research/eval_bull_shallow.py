"""
牛市浅回调隔离实验：模型在"没见过的牛市 + 剔除深度回调"上的 Precision/Recall。

目的（与用户对齐的需求）：
  验证假设——"在牛市浅回调场景里，现有 v3_n2 抓底模型其实已接近天花板，
  瓶颈在 regime（市场状态）而非特征"。

设计要点（防作弊 + 指标连续性，逐条对应需求）：
  1. 防数据泄漏：存盘的生产模型训练期含整段牛市（样本内），不可直接用。
     本脚本用 v3_n2 同一套配置（NDay2 + sl_proximity 标注 + features_v3 + 同超参），
     但训练集【只到 BULL_START 之前】（含完整 2022 熊市），完全不含这轮牛市；
     再用这个"没见过牛市"的模型预测整段牛市 → 整段牛市都是诚实样本外（OOS）。
  2. 指标连续性：特征全程在【连续未删减】的价格序列上算好（RSI 等保真实历史上下文），
     深度回调只在【计算 P/R 这一步】从样本集中剔除，绝不剪切价格再重算指标。
  3. 深度回调剔除口径：只去掉 >10% 回调的"高点→低点"下跌段（如 500→300），
     保留修复段（300→500）与浅回调（<10%）。

评估口径：label 列（= 训练口径，sl_proximity）。阈值默认 0.35（生产阈值）。

用法：
  python -m ml.research.eval_bull_shallow
  python -m ml.research.eval_bull_shallow --bull-start 2022-10-13 --dd 0.10 --thrs 0.30 0.35 0.40 0.45
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from ml.labeling import run as run_labeling, load_spy
from ml.versions import VERSIONS
from xgboost import XGBClassifier


def _make_model(model_cfg: dict) -> XGBClassifier:
    """与 train_export._make_model 完全一致的超参，保证可比。"""
    return XGBClassifier(
        n_estimators=model_cfg.get("n_estimators", 100),
        max_depth=model_cfg.get("max_depth", 4),
        learning_rate=model_cfg.get("learning_rate", 0.1),
        eval_metric="logloss",
        random_state=42,
        verbosity=0,
    )


def build_dataset(version: str = "v3_n2"):
    """加载→信号→标注→特征（连续序列上算特征），返回 (data, feature_cols)。"""
    config = VERSIONS[version]
    import importlib
    features_module = importlib.import_module(config["features_module"])

    method = config["labeling"]["method"]
    labeling_kwargs = {k: v for k, v in config["labeling"].items() if k != "method"}
    n_days = config.get("signal", {}).get("n_days", 5)

    labeled = run_labeling(n_days=n_days, method=method, **labeling_kwargs)
    spy_df = load_spy()
    data, feature_cols = features_module.build_features(labeled, spy_df)
    data = data.dropna(subset=feature_cols).reset_index(drop=True)
    return data, feature_cols, config


def find_deep_correction_dates(spy_df: pd.DataFrame, bull_start: pd.Timestamp,
                               dd_threshold: float = 0.10):
    """
    在 [bull_start, 末尾] 的【连续日线】上，识别 >dd_threshold 的深度回调"下跌段"。

    口径（与用户举例 400→500→300→500 一致）：
      只剔除"高点→低点"的下跌段（500→300），保留修复段（300→500）。
    算法：用收盘价跟踪 high-water mark（运行新高）。每段回撤的谷底 = 两个相邻新高之间的最低点；
      若 (高点-谷底)/高点 > 阈值，则把 [高点日, 谷底日] 整段标记为剔除。

    返回 (removed_dates:set, episodes:list[dict])
    """
    seg = spy_df[spy_df["date"] >= bull_start].reset_index(drop=True)
    close = seg["close"].values
    dates = seg["date"].values
    n = len(seg)

    removed_idx = set()
    episodes = []

    peak_val = close[0]
    peak_idx = 0
    trough_val = close[0]
    trough_idx = 0
    in_drawdown = False

    def _close_episode():
        if in_drawdown and (peak_val - trough_val) / peak_val > dd_threshold:
            for j in range(peak_idx, trough_idx + 1):
                removed_idx.add(j)
            episodes.append({
                "peak_date": pd.Timestamp(dates[peak_idx]),
                "peak_close": float(peak_val),
                "trough_date": pd.Timestamp(dates[trough_idx]),
                "trough_close": float(trough_val),
                "depth": (peak_val - trough_val) / peak_val,
                "downleg_days": trough_idx - peak_idx + 1,
            })

    for i in range(1, n):
        if close[i] >= peak_val:
            _close_episode()
            peak_val = close[i]; peak_idx = i
            trough_val = close[i]; trough_idx = i
            in_drawdown = False
        else:
            in_drawdown = True
            if close[i] < trough_val:
                trough_val = close[i]; trough_idx = i
    _close_episode()  # 收尾：尚未修复的进行中回调

    removed_dates = {pd.Timestamp(dates[j]) for j in removed_idx}
    return removed_dates, episodes


def _pr(y, proba, thr):
    m = proba > thr
    pos = int(y.sum())
    if m.sum() == 0 or pos == 0:
        return 0.0, 0.0, int(m.sum())
    p = float(y[m].mean())
    r = float(y[m].sum() / pos)
    return p, r, int(m.sum())


def run(bull_start="2022-10-13", dd_threshold=0.10,
        thrs=(0.30, 0.35, 0.40, 0.45), version="v3_n2"):
    from sklearn.metrics import roc_auc_score, average_precision_score

    bull_start = pd.Timestamp(bull_start)

    print("=" * 100)
    print("  牛市浅回调隔离实验（OOS：模型没见过牛市；剔除 >%.0f%% 深度回调下跌段）"
          % (dd_threshold * 100))
    print("=" * 100)

    data, feature_cols, config = build_dataset(version)
    spy_df = load_spy()

    # --- 训练/预测切分：训练只到牛市起点之前（含完整 2022 熊市），预测整段牛市 ---
    train = data[data["date"] < bull_start].reset_index(drop=True)
    test = data[data["date"] >= bull_start].reset_index(drop=True)

    print(f"\n[配置] version={version}  NDay={config.get('signal',{}).get('n_days')}  "
          f"标注={config['labeling']}  特征数={len(feature_cols)}")
    print(f"[切分] 牛市起点 = {bull_start.date()}")
    print(f"[切分] 训练样本(< 起点): {len(train)}  期: {train['date'].min().date()} ~ {train['date'].max().date()}")
    print(f"[切分] 牛市样本(>=起点): {len(test)}  期: {test['date'].min().date()} ~ {test['date'].max().date()}")

    model = _make_model(config["model"])
    model.fit(train[feature_cols].values, train["label"].values)
    test = test.copy()
    test["proba"] = model.predict_proba(test[feature_cols].values)[:, 1]

    # --- 深度回调剔除（仅影响评估样本集，不影响特征） ---
    removed_dates, episodes = find_deep_correction_dates(spy_df, bull_start, dd_threshold)
    print(f"\n[深度回调] 识别到 {len(episodes)} 段 >{dd_threshold*100:.0f}% 回调下跌段，从评估中剔除其交易日：")
    print(f"  {'高点日':>12} {'高点':>8}  {'谷底日':>12} {'谷底':>8}  {'跌幅':>7} {'下跌天数':>6}")
    for e in episodes:
        print(f"  {str(e['peak_date'].date()):>12} {e['peak_close']:>8.2f}  "
              f"{str(e['trough_date'].date()):>12} {e['trough_close']:>8.2f}  "
              f"{e['depth']*100:>6.1f}% {e['downleg_days']:>6}")

    test_shallow = test[~test["date"].isin(removed_dates)].reset_index(drop=True)
    removed_signals = len(test) - len(test_shallow)
    print(f"\n[样本] 牛市信号日 {len(test)} 个 → 剔除落在深度回调下跌段的 {removed_signals} 个 "
          f"→ 浅回调样本 {len(test_shallow)} 个")

    # --- 两个口径对比：完整牛市 OOS vs 浅回调 OOS ---
    def _report(name, df):
        y = df["label"].values
        proba = df["proba"].values
        pos = int(y.sum())
        if len(df) == 0 or len(np.unique(y)) < 2:
            print(f"\n  [{name}] 样本不足或标签单一，跳过")
            return None
        auc = roc_auc_score(y, proba)
        aucpr = average_precision_score(y, proba)
        print(f"\n  ── {name} ──")
        print(f"  样本={len(df)}  真底(label=1)={pos}  基线P(正样本率)={y.mean()*100:.1f}%  "
              f"AUC-ROC={auc:.3f}  AUC-PR={aucpr:.3f}")
        print(f"  {'阈值':>6} {'放行':>5} {'Precision':>10} {'Recall':>8}")
        for t in thrs:
            p, r, npass = _pr(y, proba, t)
            mark = "  ← 生产阈值" if abs(t - 0.35) < 1e-9 else ""
            print(f"  {t:>6.2f} {npass:>5} {p*100:>9.1f}% {r*100:>7.0f}%{mark}")
        return {"name": name, "n": len(df), "pos": pos, "base_p": float(y.mean()),
                "auc": float(auc), "auc_pr": float(aucpr)}

    print("\n" + "-" * 100)
    print("  Precision / Recall 对比（评估口径 = label 列 = 训练口径；真底 = sl_proximity 标注）")
    print("-" * 100)
    r_full = _report("A. 完整牛市 OOS（不剔除深度回调）", test)
    r_shallow = _report("B. 牛市浅回调 OOS（剔除 >%.0f%% 深度回调下跌段）" % (dd_threshold * 100),
                        test_shallow)
    test_deep = test[test["date"].isin(removed_dates)].reset_index(drop=True)
    r_deep = _report("C. 仅深度回调下跌段（被剔除的那部分，对照模型在深跌里的表现）", test_deep)

    # --- 参照：训练集（样本内，仅供对照"上限" / 注意是样本内会偏乐观） ---
    yt = train["label"].values
    if len(np.unique(yt)) > 1:
        proba_tr = model.predict_proba(train[feature_cols].values)[:, 1]
        print(f"\n  ── 参照：训练集本身（样本内，偏乐观，仅作上限参照）──")
        print(f"  样本={len(train)}  真底={int(yt.sum())}  基线P={yt.mean()*100:.1f}%  "
              f"AUC-ROC={roc_auc_score(yt, proba_tr):.3f}")

    print("\n" + "=" * 100)
    print("  解读提示：")
    print("  - 若 B（浅回调）的 P/R 明显高于 A（完整牛市），说明深度回调正是拉低模型表现的部分，")
    print("    印证'模型适合浅回调、深跌失灵'，支持双模型/regime-gate 方向。")
    print("  - 若 B 的 P/R 与历史整体（diagnosis §11：N=2 @0.35 ≈ 46.5%/80%）相近且不再上升，")
    print("    说明牛市浅回调下模型已接近天花板，继续加特征收益有限——印证你的假设。")
    print("=" * 100)

    return {"full": r_full, "shallow": r_shallow, "episodes": episodes}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bull-start", type=str, default="2022-10-13",
                   help="牛市起点（含），训练集只用此日之前的数据")
    p.add_argument("--dd", type=float, default=0.10, help="深度回调阈值（默认 0.10 = 10%）")
    p.add_argument("--thrs", type=float, nargs="+", default=[0.30, 0.35, 0.40, 0.45])
    p.add_argument("--version", type=str, default="v3_n2")
    args = p.parse_args()
    run(bull_start=args.bull_start, dd_threshold=args.dd,
        thrs=tuple(args.thrs), version=args.version)


if __name__ == "__main__":
    main()
