"""
导出已训练 ML 模型的历史回放结果。

用途：
  - 对当前生产模型 v3_n2 做日期/区间回放。
  - 对历史 worktree 中的原版 v3 做同样回放。

本脚本只加载已导出的模型，不训练模型；输出 JSON 供交互式图表使用。
"""
# pyright: reportMissingImports=false
from __future__ import annotations

import argparse
import importlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from xgboost import XGBClassifier


DEFAULT_SHAP_DATES = [
    "2026-06-09",
    "2026-06-10",
    "2026-06-11",
    "2026-06-25",
    "2026-06-26",
]


def _json_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(v):
        return None
    return v


def _json_bool(value: Any) -> bool:
    return bool(value)


def _read_freshness(data_root: Path) -> dict[str, str | None]:
    sources = {
        "SPY": "SPY_adjusted.csv",
        "VIX": "vix_daily.csv",
        "breadth": "sp500_breadth.csv",
    }
    freshness: dict[str, str | None] = {}
    for name, filename in sources.items():
        path = data_root / filename
        if not path.exists():
            freshness[name] = None
            continue
        df = pd.read_csv(path)
        date_col = "时间" if "时间" in df.columns else "date"
        freshness[name] = str(df[date_col].iloc[-1])
    return freshness


def _load_target_modules(repo_root: Path, data_root: Path):
    """按 repo_root 加载目标版本代码，并把数据目录指到 data_root。"""
    sys.path.insert(0, str(repo_root))

    versions = importlib.import_module("ml.versions")
    labeling = importlib.import_module("ml.labeling")
    labeling.DATA_DIR = data_root

    return versions, labeling


def _load_model(repo_root: Path, version: str, n_days: int) -> tuple[XGBClassifier, dict]:
    model_path = repo_root / "models" / f"spy_nday{n_days}_{version}.ubj"
    meta_path = repo_root / "models" / f"spy_nday{n_days}_{version}.json"
    if not model_path.exists():
        raise FileNotFoundError(f"模型文件不存在: {model_path}")
    if not meta_path.exists():
        raise FileNotFoundError(f"元数据不存在: {meta_path}")

    model = XGBClassifier()
    model.load_model(str(model_path))
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    return model, meta


def _compute_shap(model: XGBClassifier, X: np.ndarray, feature_cols: list[str]) -> tuple[dict[str, float], float]:
    import xgboost as xgb

    booster = model.get_booster()
    dmatrix = xgb.DMatrix(X, feature_names=list(feature_cols))
    contribs = booster.predict(dmatrix, pred_contribs=True)[0]
    bias = float(contribs[-1])
    values = {col: float(contribs[i]) for i, col in enumerate(feature_cols)}
    return values, bias


def _top_shap(contribs: dict[str, float], feature_values: dict[str, float | None]) -> dict[str, list[dict[str, float | str | None]]]:
    positives = sorted(
        ((k, v) for k, v in contribs.items() if v > 0),
        key=lambda kv: kv[1],
        reverse=True,
    )[:5]
    negatives = sorted(
        ((k, v) for k, v in contribs.items() if v < 0),
        key=lambda kv: kv[1],
    )[:5]

    def pack(items):
        return [
            {
                "feature": name,
                "shap": _json_float(value),
                "value": feature_values.get(name),
            }
            for name, value in items
        ]

    return {"positive": pack(positives), "negative": pack(negatives)}


def export_replay(
    *,
    repo_root: Path,
    data_root: Path,
    version: str,
    start: str,
    end: str | None,
    output: Path,
    threshold: float | None,
    shap_dates: list[str],
) -> dict:
    repo_root = repo_root.resolve()
    data_root = data_root.resolve()
    versions, labeling = _load_target_modules(repo_root, data_root)

    config = versions.VERSIONS[version]
    n_days = int(config.get("signal", {}).get("n_days", 5))
    threshold_default = float(threshold if threshold is not None else (0.35 if version == "v3_n2" else 0.50))

    model, meta = _load_model(repo_root, version, n_days)
    feature_cols = list(meta["feature_cols"])
    features_module = importlib.import_module(meta["features_module"])
    if hasattr(features_module, "DATA_DIR"):
        features_module.DATA_DIR = data_root

    spy_df = labeling.load_spy()
    pseudo_labeled = pd.DataFrame({
        "date": spy_df["date"].values,
        "label": 0,
        "forward_return": 0.0,
    })
    data, cols = features_module.build_features(pseudo_labeled, spy_df)
    if cols != feature_cols:
        missing = sorted(set(feature_cols) - set(cols))
        extra = sorted(set(cols) - set(feature_cols))
        raise ValueError(f"特征列与模型元数据不一致: missing={missing} extra={extra}")

    data_valid = data.dropna(subset=feature_cols).copy()
    data_valid = data_valid.merge(
        spy_df[["date", "open", "high", "low", "close", "volume"]],
        on="date",
        how="left",
    )

    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end) if end else pd.Timestamp(data_valid["date"].max())
    data_valid = data_valid[(data_valid["date"] >= start_ts) & (data_valid["date"] <= end_ts)].copy()
    data_valid = data_valid.sort_values("date").reset_index(drop=True)
    if data_valid.empty:
        raise RuntimeError(f"指定区间无可预测数据: {start} ~ {end or 'latest'}")

    X = data_valid[feature_cols].values.astype(float)
    probabilities = model.predict_proba(X)[:, 1]

    signal_series = labeling.generate_nday_signals(spy_df, n=n_days)
    signal_map = dict(zip(spy_df["date"], signal_series))
    ema_ctx = labeling.compute_backtest_ema_context(spy_df, ema_period=20)
    consec_map = dict(zip(spy_df["date"], ema_ctx["consecutive_below_ema"]))

    shap_date_set = {pd.Timestamp(d).strftime("%Y-%m-%d") for d in shap_dates}
    rows = []
    for idx, row in data_valid.iterrows():
        date_str = pd.Timestamp(row["date"]).strftime("%Y-%m-%d")
        proba = float(probabilities[idx])
        is_signal_day = _json_bool(signal_map.get(pd.Timestamp(row["date"]), False))
        feature_values = {col: _json_float(row[col]) for col in feature_cols}
        record = {
            "date": date_str,
            "open": _json_float(row.get("open")),
            "high": _json_float(row.get("high")),
            "low": _json_float(row.get("low")),
            "close": _json_float(row.get("close")),
            "volume": int(row["volume"]) if pd.notna(row.get("volume")) else None,
            "probability": proba,
            "n_days": n_days,
            "is_signal_day": is_signal_day,
            "consecutive_below_ema": int(consec_map.get(pd.Timestamp(row["date"]), 0)),
            "threshold_default": threshold_default,
            "buy_default": is_signal_day and proba >= threshold_default,
            "buy_at_035": is_signal_day and proba >= 0.35,
            "feature_values": feature_values if date_str in shap_date_set else None,
            "shap": None,
        }

        if date_str in shap_date_set:
            sample = row[feature_cols].values.astype(float).reshape(1, -1)
            contribs, bias = _compute_shap(model, sample, feature_cols)
            record["shap"] = {
                "bias": _json_float(bias),
                "total": _json_float(sum(contribs.values())),
                "top": _top_shap(contribs, feature_values),
            }
        rows.append(record)

    latest = rows[-1]
    payload = {
        "version": version,
        "repo_root": str(repo_root),
        "data_root": str(data_root),
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "start": pd.Timestamp(data_valid["date"].min()).strftime("%Y-%m-%d"),
        "end": pd.Timestamp(data_valid["date"].max()).strftime("%Y-%m-%d"),
        "threshold_default": threshold_default,
        "threshold_reference": 0.35,
        "n_days": n_days,
        "data_freshness": _read_freshness(data_root),
        "model_meta": {
            "model_file": meta.get("model_file"),
            "trained_at_utc": meta.get("trained_at_utc"),
            "train_period": meta.get("train_period"),
            "train_pos_rate": meta.get("train_pos_rate"),
            "holdout_metrics": meta.get("holdout_metrics", {}),
        },
        "latest": latest,
        "rows": rows,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[Output] {output}")
    print(
        f"[Replay] {version} {payload['start']} ~ {payload['end']} "
        f"rows={len(rows)} latest={latest['date']} p={latest['probability']:.1%} "
        f"signal={latest['is_signal_day']} buy={latest['buy_default']}"
    )
    return payload


def main():
    parser = argparse.ArgumentParser(description="导出已训练 ML 模型的历史回放 JSON")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--data-root", type=Path, default=Path(__file__).resolve().parent.parent / "data")
    parser.add_argument("--version", required=True)
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--shap-dates", nargs="*", default=DEFAULT_SHAP_DATES)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    export_replay(
        repo_root=args.repo_root,
        data_root=args.data_root,
        version=args.version,
        start=args.start,
        end=args.end,
        output=args.output,
        threshold=args.threshold,
        shap_dates=args.shap_dates,
    )


if __name__ == "__main__":
    main()
