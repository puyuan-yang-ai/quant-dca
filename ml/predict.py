"""
每日推理 — 加载导出的模型，对最新交易日输出预测概率

与训练分离：本脚本只加载 models/ 下已导出的模型，不做任何训练。
可独立部署到 Mac mini（只需 pandas/numpy/xgboost + data/ + models/ + src/ + ml/）。

使用：
  cd /home/puyuyang/workspace/projects/study/quant-dca
  python -m ml.predict                       # 用激活版本模型，预测最新交易日
  python -m ml.predict --version v3          # 指定模型版本
  python -m ml.predict --json out.json       # 同时把结果写成 JSON（供报告脚本消费）

输出说明：
  - probability:   模型给出的"该日处于底部区域"的概率
  - is_signal_day: 今天是否满足 NDay5 条件（连续 5 天收盘在 EMA20 下方）
                   ⚠️ 模型只在信号日样本上训练。非信号日的概率仅供参考，
                   属于模型未见过的输入分布，不可作为交易依据。
  - data_freshness: 各数据源最新日期，用于判断是否有数据延迟（ffill 陈旧风险）
"""
import argparse
import importlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from xgboost import XGBClassifier

from ml.labeling import load_spy, generate_nday_signals
from ml.versions import ACTIVE_VERSION

MODELS_DIR = Path(__file__).parent.parent / "models"
DATA_DIR = Path(__file__).parent.parent / "data"


def load_model_and_meta(version: str):
    """加载模型文件与元数据，返回 (model, meta)"""
    from ml.versions import VERSIONS
    n_days = VERSIONS.get(version, {}).get("signal", {}).get("n_days", 5)
    model_path = MODELS_DIR / f"spy_nday{n_days}_{version}.ubj"
    meta_path = MODELS_DIR / f"spy_nday{n_days}_{version}.json"
    if not model_path.exists():
        raise FileNotFoundError(
            f"模型文件不存在: {model_path}\n请先运行 python -m ml.train_export --version {version}"
        )
    if not meta_path.exists():
        raise FileNotFoundError(f"元数据不存在: {meta_path}")

    model = XGBClassifier()
    model.load_model(str(model_path))
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    return model, meta


def _build_all_day_features(features_module, feature_cols: list[str]) -> pd.DataFrame:
    """
    为【每一个交易日】构造特征（而非只为信号日）。

    features 模块的 build_features 用 labeled_df["date"] 决定返回哪些日期的特征。
    推理时我们想要所有日期，所以传入一个覆盖全历史的伪标注表（label 占位）。
    特征本身是全序列计算的，因此最后一行就是"今天"的真实特征向量。
    """
    spy_df = load_spy()
    pseudo_labeled = pd.DataFrame({
        "date": spy_df["date"].values,
        "label": 0,             # 占位，推理不使用
        "forward_return": 0.0,  # 占位，推理不使用
    })
    data, cols = features_module.build_features(pseudo_labeled, spy_df)

    # 校验特征契约：推理特征顺序必须与训练元数据完全一致
    if cols != feature_cols:
        missing = set(feature_cols) - set(cols)
        extra = set(cols) - set(feature_cols)
        raise ValueError(
            "特征列与训练元数据不一致，模型与特征模块版本可能不匹配。\n"
            f"  缺失: {missing}\n  多余: {extra}\n"
            "请确认 versions.py 的 features_module 与导出模型时一致。"
        )
    return data, spy_df


def _data_freshness() -> dict:
    """读取各数据源最新日期，用于标注数据新鲜度"""
    freshness = {}
    sources = {
        "SPY": "SPY_adjusted.csv",
        "VIX": "vix_daily.csv",
        "breadth": "sp500_breadth.csv",
    }
    for name, fname in sources.items():
        path = DATA_DIR / fname
        if not path.exists():
            freshness[name] = None
            continue
        df = pd.read_csv(path)
        date_col = "时间" if "时间" in df.columns else "date"
        freshness[name] = str(df[date_col].iloc[-1])
    return freshness


def _compute_shap(model, X: np.ndarray, feature_cols: list[str]) -> tuple[dict, float]:
    """
    计算单样本 TreeSHAP 归因，使用 xgboost 原生 pred_contribs（无需安装 shap 库）。

    返回 (contribs_dict, bias)：
      - contribs_dict: {特征名: SHAP 贡献值}，单位为 margin / log-odds 空间
      - bias: 基准项（全样本期望 logit），sum(contribs) + bias = 该样本的 logit
    正贡献 = 把"底部概率"往上推；负贡献 = 往下压。
    """
    import xgboost as xgb

    booster = model.get_booster()
    dmatrix = xgb.DMatrix(X, feature_names=list(feature_cols))
    # pred_contribs=True 返回形状 (n_samples, n_features + 1)，最后一列是 bias
    contribs = booster.predict(dmatrix, pred_contribs=True)
    row = contribs[0]
    bias = float(row[-1])
    contribs_dict = {col: float(row[i]) for i, col in enumerate(feature_cols)}
    return contribs_dict, bias


def predict_latest(version: str = None) -> dict:
    """对最新交易日做预测，返回结果字典"""
    version = version or ACTIVE_VERSION
    model, meta = load_model_and_meta(version)
    feature_cols = meta["feature_cols"]

    features_module = importlib.import_module(meta["features_module"])
    data, spy_df = _build_all_day_features(features_module, feature_cols)

    # 取最新一行有完整特征的记录
    data_valid = data.dropna(subset=feature_cols)
    if data_valid.empty:
        raise RuntimeError("没有任何一行的特征完整，无法预测")
    latest = data_valid.iloc[-1]
    latest_date = pd.Timestamp(latest["date"])

    X = latest[feature_cols].values.astype(float).reshape(1, -1)
    proba = float(model.predict_proba(X)[0, 1])

    # 逐样本 SHAP 归因（TreeSHAP，来自 xgboost 原生 pred_contribs，无需额外安装 shap 库）
    # 贡献值在 margin / log-odds 空间：sum(contribs) + bias = 模型输出的 logit
    shap_contribs, shap_bias = _compute_shap(model, X, feature_cols)

    # 今天是否满足 NDay 信号条件（门槛取自版本配置，默认 5）
    from ml.versions import VERSIONS
    n_days = VERSIONS.get(version, {}).get("signal", {}).get("n_days", 5)
    signal_series = generate_nday_signals(spy_df, n=n_days)
    signal_map = dict(zip(spy_df["date"], signal_series))
    is_signal_day = bool(signal_map.get(latest_date, False))

    # 距离触发还差几天（consecutive_below_ema 当前值 vs n_days）
    from ml.labeling import compute_backtest_ema_context
    ema_ctx = compute_backtest_ema_context(spy_df, ema_period=20)
    consec_below = int(ema_ctx["consecutive_below_ema"].iloc[-1]) if latest_date == spy_df["date"].iloc[-1] else None

    feature_values = {col: float(latest[col]) for col in feature_cols}
    importance = meta.get("feature_importance", {})

    result = {
        "version": version,
        "predicted_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of_date": latest_date.strftime("%Y-%m-%d"),
        "probability": proba,
        "is_signal_day": is_signal_day,
        "consecutive_below_ema": consec_below,
        "days_to_signal": (n_days - consec_below) if (consec_below is not None and consec_below < n_days) else 0,
        "spy_close": float(latest["close"]) if "close" in latest else float(spy_df["close"].iloc[-1]),
        "feature_values": feature_values,
        "feature_importance": importance,
        "shap_contribs": shap_contribs,
        "shap_bias": shap_bias,
        "data_freshness": _data_freshness(),
        "train_period": meta.get("train_period"),
        "train_pos_rate": meta.get("train_pos_rate"),
        "holdout_metrics": meta.get("holdout_metrics", {}),
    }
    return result


def _print_report(r: dict):
    """终端可读输出"""
    print("\n" + "=" * 60)
    print(f"  SPY NDay5 底部信号 — 每日预测 ({r['as_of_date']})")
    print("=" * 60)

    signal_tag = "✅ 是信号日 (满足 NDay5)" if r["is_signal_day"] else "❌ 非信号日"
    print(f"  数据截止:     {r['as_of_date']}   SPY 收盘: {r['spy_close']:.2f}")
    print(f"  NDay5 状态:   {signal_tag}")
    if not r["is_signal_day"] and r["consecutive_below_ema"] is not None:
        print(f"                连续低于 EMA20: {r['consecutive_below_ema']} 天 "
              f"(还差 {r['days_to_signal']} 天触发)")
    print(f"  底部区域概率: {r['probability']:.1%}")

    if not r["is_signal_day"]:
        print(f"  ⚠️  今日非信号日，模型未在此场景训练，以上概率仅供参考，不可作为交易依据。")

    ho = r.get("holdout_metrics") or {}
    if ho.get("auc_roc"):
        print(f"\n  [模型可靠性] 样本外 AUC-ROC={ho['auc_roc']:.3f} "
              f"(0.5=瞎猜, 越接近1越好；当前为弱信号)")

    print(f"\n  [数据新鲜度] " + "  ".join(
        f"{k}={v}" for k, v in r["data_freshness"].items()))

    # feature importance Top + 当前值
    imp = r["feature_importance"]
    fv = r["feature_values"]
    if imp:
        print(f"\n  [Top 特征重要度 & 当前取值]")
        top = sorted(imp.items(), key=lambda kv: kv[1], reverse=True)[:8]
        print(f"    {'特征':<26} {'重要度':>8}  {'当前值':>10}")
        print(f"    {'-'*48}")
        for name, val in top:
            cur = fv.get(name, float('nan'))
            print(f"    {name:<26} {val:>8.4f}  {cur:>10.3f}")

    # 逐样本 SHAP 归因：本日各特征把"底部概率"往上推(+)还是往下压(-)
    contribs = r.get("shap_contribs") or {}
    if contribs:
        bias = r.get("shap_bias", 0.0)
        ordered = sorted(contribs.items(), key=lambda kv: abs(kv[1]), reverse=True)
        total = sum(contribs.values())
        print(f"\n  [SHAP 逐样本归因 — 对数几率(log-odds)空间，按影响力排序]")
        print(f"    基准 bias = {bias:+.3f}   特征贡献合计 = {total:+.3f}   "
              f"样本 logit = {bias + total:+.3f}")
        print(f"    （正=推高底部概率  负=压低底部概率）")
        print(f"    {'特征':<26} {'SHAP贡献':>10}  {'当前值':>10}")
        print(f"    {'-'*50}")
        for name, val in ordered[:10]:
            cur = fv.get(name, float('nan'))
            arrow = "↑" if val > 0 else ("↓" if val < 0 else " ")
            print(f"    {name:<26} {val:>+10.4f}{arrow} {cur:>10.3f}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="每日推理：预测最新交易日的底部概率")
    parser.add_argument("--version", type=str, default=None,
                        help="模型版本（默认用 versions.py 的 ACTIVE_VERSION）")
    parser.add_argument("--json", type=str, default=None,
                        help="把结果写入指定 JSON 文件（供报告脚本消费）")
    args = parser.parse_args()

    result = predict_latest(version=args.version)
    _print_report(result)

    if args.json:
        out_path = Path(args.json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n[Output] 结果已写入 {out_path}")


if __name__ == "__main__":
    main()
