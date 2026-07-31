"""
空间 GT 两阶段端到端检测评估。

主口径：
1. 全部交易日作为评价全集；
2. Stage 1 未产生 NDay2 候选的 GT 日也计入 FN；
3. Stage 2 使用 walk-forward OOS 训练分位阈值 q=0.5；
4. Precision / Recall / F1 为主，Accuracy 仅作辅助；
5. 同时报告连续信号并簇后的事件级 Precision / Recall / F1。
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from ml.research.eval_spatial_e2e import _walk_forward_rank
from ml.research.eval_spatial_gt import (
    HORIZON_DAYS,
    _build_base_data,
    _event_members,
    _load_stored_v3_n2_oos,
    _sl_centers,
    _spatial_target,
)
from ml.versions import VERSIONS
from ml.walk_forward import make_expanding_folds, purge_embargo_mask

ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = ROOT / "output"
FINAL_PCT = 0.008
FINAL_LAMBDA = 0.25
RANK_THRESHOLD = 0.5
BOOTSTRAP_SAMPLES = 2_000


def _binary_metrics(target, predicted):
    """计算稀有事件检测的完整混淆矩阵与主指标。"""
    target = np.asarray(target, dtype=bool)
    predicted = np.asarray(predicted, dtype=bool)
    tp = int(np.sum(target & predicted))
    fp = int(np.sum(~target & predicted))
    fn = int(np.sum(target & ~predicted))
    tn = int(np.sum(~target & ~predicted))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "accuracy": float((tp + tn) / len(target)),
        "specificity": float(tn / (tn + fp)) if tn + fp else 0.0,
        "gt_base_rate": float(target.mean()),
        "precision_lift": (
            float(precision / target.mean())
            if target.mean() > 0
            else float("nan")
        ),
    }


def _signal_clusters(indices):
    """把连续交易日上的最终信号并为一个预测事件。"""
    indices = np.sort(np.asarray(indices, dtype=int))
    if len(indices) == 0:
        return []
    boundaries = np.flatnonzero(np.diff(indices) > 1) + 1
    return [
        chunk
        for chunk in np.split(indices, boundaries)
        if len(chunk)
    ]


def _event_metrics(target, predicted, centers, members, start_idx, end_idx):
    """按完整 SL7 事件和连续预测簇计算事件级 P/R/F1。"""
    target = np.asarray(target, dtype=bool)
    predicted = np.asarray(predicted, dtype=bool)
    predicted_indices = np.flatnonzero(predicted) + start_idx
    target_indices = np.flatnonzero(target) + start_idx
    clusters = _signal_clusters(predicted_indices)
    target_set = set(int(value) for value in target_indices)
    hit_clusters = sum(
        any(int(index) in target_set for index in cluster)
        for cluster in clusters
    )

    period_centers = centers[
        (centers - 7 >= start_idx)
        & (centers + 7 <= end_idx)
    ]
    predicted_set = set(int(value) for value in predicted_indices)
    hit_events = sum(
        any(int(index) in predicted_set for index in members[int(center)])
        for center in period_centers
    )
    precision = hit_clusters / len(clusters) if clusters else 0.0
    recall = hit_events / len(period_centers) if len(period_centers) else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return {
        "predicted_clusters": int(len(clusters)),
        "hit_clusters": int(hit_clusters),
        "gt_events": int(len(period_centers)),
        "hit_events": int(hit_events),
        "event_precision": float(precision),
        "event_recall": float(recall),
        "event_f1": float(f1),
    }


def _gt_assignments(spy, centers):
    """给每个交易日记录价格溢价最小的 SL7 中心，供人工审核。"""
    close = spy["close"].astype(float).to_numpy()
    best_premium = np.full(len(spy), np.nan)
    best_center = np.full(len(spy), -1, dtype=int)
    for center in centers:
        bars = np.arange(max(0, center - 7), min(len(spy), center + 8))
        premium = close[bars] / close[center] - 1
        current = best_premium[bars]
        better = np.isnan(current) | (premium < current)
        update = bars[better]
        best_premium[update] = premium[better]
        best_center[update] = int(center)
    return best_premium, best_center


def _daily_arrays(spy, data, spatial, stored):
    """把候选级 OOS 结果投影回全部交易日。"""
    n_days = len(spy)
    spatial_valid = spatial["proba"].notna().to_numpy()
    stored_valid = stored["proba"].notna().to_numpy()
    common_candidate = spatial_valid & stored_valid
    spy_indices = data["spy_idx"].to_numpy(int)

    arrays = {}
    for scope, candidate_mask in [
        ("new_oos", spatial_valid),
        ("common_oos", common_candidate),
    ]:
        stage1 = np.zeros(n_days, dtype=bool)
        new_pred = np.zeros(n_days, dtype=bool)
        new_score = np.zeros(n_days, dtype=float)
        stage1[spy_indices[candidate_mask]] = True
        new_selected = (
            candidate_mask
            & (
                spatial["train_percentile"].to_numpy(float)
                >= RANK_THRESHOLD
            )
        )
        new_pred[spy_indices[new_selected]] = True
        new_score[spy_indices[candidate_mask]] = spatial.loc[
            candidate_mask,
            "train_percentile",
        ].to_numpy(float)
        arrays[f"{scope}_stage1"] = stage1
        arrays[f"{scope}_new_pred"] = new_pred
        arrays[f"{scope}_new_score"] = new_score

    old_pred = np.zeros(n_days, dtype=bool)
    old_score = np.zeros(n_days, dtype=float)
    old_pred[spy_indices[stored_valid & stored["passed"].to_numpy(bool)]] = True
    old_score[spy_indices[stored_valid]] = stored.loc[
        stored_valid,
        "proba",
    ].to_numpy(float)
    arrays["common_oos_old_pred"] = old_pred
    arrays["common_oos_old_score"] = old_score
    return arrays, spatial_valid, common_candidate


def _period_row(
    period,
    variant,
    spy,
    target,
    predicted,
    score,
    centers,
    members,
    start,
    end,
):
    dates = pd.to_datetime(spy["date"])
    mask = (
        (dates >= pd.Timestamp(start))
        & (dates <= pd.Timestamp(end))
    ).to_numpy()
    positions = np.flatnonzero(mask)
    y = target[mask]
    pred = predicted[mask]
    metrics = _binary_metrics(y, pred)
    event = _event_metrics(
        y,
        pred,
        centers,
        members,
        int(positions.min()),
        int(positions.max()),
    )
    return {
        "period": period,
        "variant": variant,
        "start": dates.iloc[positions.min()].strftime("%Y-%m-%d"),
        "end": dates.iloc[positions.max()].strftime("%Y-%m-%d"),
        "trading_days": int(mask.sum()),
        "predicted_days": int(pred.sum()),
        "gt_days": int(y.sum()),
        "pr_auc": float(average_precision_score(y, score[mask])),
        **metrics,
        **event,
    }


def _bootstrap(
    spy,
    target,
    baseline,
    challenger,
    start,
    end,
    n_bootstrap=BOOTSTRAP_SAMPLES,
    seed=42,
):
    """按年份成块重采样日级端到端 P/R/F1 差值。"""
    dates = pd.to_datetime(spy["date"])
    mask = (
        (dates >= pd.Timestamp(start))
        & (dates <= pd.Timestamp(end))
    ).to_numpy()
    detail = pd.DataFrame({
        "year": dates[mask].dt.year.to_numpy(),
        "target": target[mask],
        "baseline": baseline[mask],
        "challenger": challenger[mask],
    })
    years = np.sort(detail["year"].unique())
    rng = np.random.default_rng(seed)
    rows = []

    baseline_metrics = _binary_metrics(detail["target"], detail["baseline"])
    challenger_metrics = _binary_metrics(
        detail["target"],
        detail["challenger"],
    )
    for metric in ["precision", "recall", "f1"]:
        differences = []
        for _ in range(n_bootstrap):
            sampled_years = rng.choice(years, size=len(years), replace=True)
            sample = pd.concat(
                [detail[detail["year"] == year] for year in sampled_years],
                ignore_index=True,
            )
            old_value = _binary_metrics(
                sample["target"],
                sample["baseline"],
            )[metric]
            new_value = _binary_metrics(
                sample["target"],
                sample["challenger"],
            )[metric]
            differences.append(new_value - old_value)
        rows.append({
            "metric": metric,
            "baseline_value": baseline_metrics[metric],
            "challenger_value": challenger_metrics[metric],
            "difference": challenger_metrics[metric] - baseline_metrics[metric],
            "ci_low": float(np.quantile(differences, 0.025)),
            "ci_high": float(np.quantile(differences, 0.975)),
            "bootstrap_samples": int(n_bootstrap),
        })
    return pd.DataFrame(rows)


def _review_frame(
    spy,
    data,
    gt,
    centers,
    spatial,
    spatial_valid,
):
    """导出全部新模型 OOS 交易日，供交互图表和人工审核使用。"""
    dates = pd.to_datetime(spy["date"]).reset_index(drop=True)
    spy_indices = data["spy_idx"].to_numpy(int)
    valid_indices = spy_indices[spatial_valid]
    start_idx = int(valid_indices.min())
    end_idx = int(valid_indices.max())
    frame = spy.iloc[start_idx:end_idx + 1][
        ["date", "open", "high", "low", "close", "volume"]
    ].copy()
    frame["spy_idx"] = np.arange(start_idx, end_idx + 1)

    premium, assigned_center = _gt_assignments(spy, centers)
    frame["is_gt"] = gt.loc[
        frame["spy_idx"],
        "is_sl_price_gt",
    ].to_numpy(bool)
    frame["sl_price_premium"] = premium[frame["spy_idx"]]
    frame["price_quality"] = gt.loc[
        frame["spy_idx"],
        "price_quality",
    ].to_numpy(float)
    frame["sl_distance"] = gt.loc[
        frame["spy_idx"],
        "sl_distance",
    ].to_numpy(float)
    frame["sl_center_date"] = [
        dates.iloc[index].strftime("%Y-%m-%d") if index >= 0 else ""
        for index in assigned_center[frame["spy_idx"]]
    ]
    center_set = set(int(center) for center in centers)
    frame["is_sl_center"] = frame["spy_idx"].isin(center_set)

    candidate_map = {
        int(spy_idx): int(data_idx)
        for data_idx, spy_idx in enumerate(spy_indices)
        if spatial_valid[data_idx]
    }
    frame["is_stage1"] = frame["spy_idx"].isin(candidate_map)
    frame["oos_probability"] = np.nan
    frame["train_percentile"] = np.nan
    frame["fold_id"] = -1
    for row_index, spy_idx in zip(frame.index, frame["spy_idx"]):
        data_idx = candidate_map.get(int(spy_idx))
        if data_idx is None:
            continue
        frame.at[row_index, "oos_probability"] = float(
            spatial.iloc[data_idx]["proba"]
        )
        frame.at[row_index, "train_percentile"] = float(
            spatial.iloc[data_idx]["train_percentile"]
        )
        frame.at[row_index, "fold_id"] = int(spatial.iloc[data_idx]["fold_id"])

    frame["is_predicted"] = (
        frame["is_stage1"]
        & (frame["train_percentile"] >= RANK_THRESHOLD)
    )
    frame["outcome"] = np.select(
        [
            frame["is_predicted"] & frame["is_gt"],
            frame["is_predicted"] & ~frame["is_gt"],
            ~frame["is_predicted"] & frame["is_gt"],
        ],
        ["TP", "FP", "FN"],
        default="TN",
    )
    frame["date"] = pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d")
    return frame.reset_index(drop=True)


def run(n_bootstrap=BOOTSTRAP_SAMPLES):
    spy, _, data, feature_cols = _build_base_data()
    dates = pd.to_datetime(data["date"]).reset_index(drop=True)
    X = data[feature_cols].to_numpy()
    spatial_y, _, quality, gt = _spatial_target(spy, data, FINAL_PCT)
    centers, members = _event_members(spy, FINAL_PCT)
    folds = make_expanding_folds(
        dates,
        n_folds=4,
        min_train=max(20, int(len(data) * 0.4)),
    )
    spatial = _walk_forward_rank(
        X,
        spatial_y,
        dates,
        folds,
        VERSIONS["v3_n2"]["model"],
        quality=quality,
        price_lambda=FINAL_LAMBDA,
    )
    stored = _load_stored_v3_n2_oos(data)
    arrays, spatial_valid, common_candidate = _daily_arrays(
        spy,
        data,
        spatial,
        stored,
    )
    target = gt["is_sl_price_gt"].to_numpy(bool)
    spy_indices = data["spy_idx"].to_numpy(int)
    common_indices = spy_indices[common_candidate]
    spatial_indices = spy_indices[spatial_valid]
    spy_dates = pd.to_datetime(spy["date"])

    common_start = spy_dates.iloc[int(common_indices.min())].strftime("%Y-%m-%d")
    common_end = spy_dates.iloc[int(common_indices.max())].strftime("%Y-%m-%d")
    new_start = spy_dates.iloc[int(spatial_indices.min())].strftime("%Y-%m-%d")
    new_end = spy_dates.iloc[int(spatial_indices.max())].strftime("%Y-%m-%d")
    final_end = min(common_end, "2026-04-02")

    rows = []
    period_specs = [
        ("development", common_start, "2019-12-31", "common"),
        ("final_test", "2020-01-01", final_end, "common"),
        ("all_common_oos", common_start, common_end, "common"),
        ("all_new_oos", new_start, new_end, "new"),
    ]
    for period, start, end, scope in period_specs:
        if scope == "common":
            variants = [
                (
                    "stage1_nday2",
                    arrays["common_oos_stage1"],
                    arrays["common_oos_stage1"].astype(float),
                ),
                (
                    "v3_n2_stored_oos",
                    arrays["common_oos_old_pred"],
                    arrays["common_oos_old_score"],
                ),
                (
                    "spatial_p0080_l025_q50",
                    arrays["common_oos_new_pred"],
                    arrays["common_oos_new_score"],
                ),
            ]
        else:
            variants = [
                (
                    "stage1_nday2",
                    arrays["new_oos_stage1"],
                    arrays["new_oos_stage1"].astype(float),
                ),
                (
                    "spatial_p0080_l025_q50",
                    arrays["new_oos_new_pred"],
                    arrays["new_oos_new_score"],
                ),
            ]
        for variant, predicted, score in variants:
            rows.append(
                _period_row(
                    period,
                    variant,
                    spy,
                    target,
                    predicted,
                    score,
                    centers,
                    members,
                    start,
                    end,
                )
            )
    summary = pd.DataFrame(rows)

    bootstrap_old = _bootstrap(
        spy,
        target,
        arrays["common_oos_old_pred"],
        arrays["common_oos_new_pred"],
        "2020-01-01",
        final_end,
        n_bootstrap=n_bootstrap,
    )
    bootstrap_old.insert(0, "baseline", "v3_n2_stored_oos")
    bootstrap_stage1 = _bootstrap(
        spy,
        target,
        arrays["common_oos_stage1"],
        arrays["common_oos_new_pred"],
        "2020-01-01",
        final_end,
        n_bootstrap=n_bootstrap,
    )
    bootstrap_stage1.insert(0, "baseline", "stage1_nday2")
    bootstrap = pd.concat(
        [bootstrap_old, bootstrap_stage1],
        ignore_index=True,
    )
    bootstrap.insert(1, "challenger", "spatial_p0080_l025_q50")

    review = _review_frame(
        spy,
        data,
        gt,
        centers,
        spatial,
        spatial_valid,
    )

    fold_meta = []
    for fold_id, (train_idx, test_idx) in enumerate(folds):
        keep = np.asarray(
            purge_embargo_mask(
                dates.iloc[train_idx],
                dates.iloc[test_idx],
                HORIZON_DAYS,
            )
        )
        train = train_idx[keep]
        fold_meta.append({
            "fold_id": int(fold_id),
            "train_start": dates.iloc[train].min().strftime("%Y-%m-%d"),
            "train_end": dates.iloc[train].max().strftime("%Y-%m-%d"),
            "test_start": dates.iloc[test_idx].min().strftime("%Y-%m-%d"),
            "test_end": dates.iloc[test_idx].max().strftime("%Y-%m-%d"),
        })
    meta = {
        "purpose": "空间 GT 两阶段端到端检测评估与人工审核数据",
        "gt": {
            "sl_n": 7,
            "pct": FINAL_PCT,
            "price_lambda": FINAL_LAMBDA,
        },
        "stage1": "NDay2",
        "stage2": "XGBoost features_v3 walk-forward OOS",
        "threshold": {
            "type": "相对本折训练概率的分位数",
            "value": RANK_THRESHOLD,
        },
        "common_oos_period": [common_start, common_end],
        "new_oos_period": [new_start, new_end],
        "final_test_period": ["2020-01-01", final_end],
        "bootstrap_samples": int(n_bootstrap),
        "folds": fold_meta,
        "notes": [
            "Recall 分母为评价期全部空间 GT 日，Stage 1 漏掉的 GT 计入 FN。",
            "Accuracy 因 TN 数量很大仅作辅助，主指标为 Precision/Recall/F1。",
            "事件级预测单位为连续交易日最终信号形成的信号簇。",
        ],
    }

    OUTPUT_DIR.mkdir(exist_ok=True)
    summary_path = OUTPUT_DIR / "spatial_gt_detection_summary.csv"
    bootstrap_path = OUTPUT_DIR / "spatial_gt_detection_bootstrap.csv"
    review_path = OUTPUT_DIR / "spatial_gt_detection_review.csv"
    meta_path = OUTPUT_DIR / "spatial_gt_detection_meta.json"
    summary.to_csv(summary_path, index=False)
    bootstrap.to_csv(bootstrap_path, index=False)
    review.to_csv(review_path, index=False)
    with open(meta_path, "w", encoding="utf-8") as file:
        json.dump(meta, file, ensure_ascii=False, indent=2)

    display = summary[
        summary["period"].isin(["final_test", "all_new_oos"])
    ][[
        "period",
        "variant",
        "precision",
        "recall",
        "f1",
        "event_precision",
        "event_recall",
        "event_f1",
        "predicted_days",
        "gt_days",
    ]]
    print(display.to_string(index=False))
    print("\n[年份块 Bootstrap]")
    print(bootstrap.to_string(index=False))
    print(f"\n[输出] {summary_path}")
    print(f"[输出] {bootstrap_path}")
    print(f"[输出] {review_path}")
    print(f"[输出] {meta_path}")
    return {
        "summary": summary,
        "bootstrap": bootstrap,
        "review": review,
        "meta": meta,
    }


def main():
    run()


if __name__ == "__main__":
    main()
