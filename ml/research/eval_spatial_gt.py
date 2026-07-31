"""
空间 GT 参数遍历、价格权重消融与 v3_n2 公平对比。

共同约定：
1. 初级候选固定为 NDay2，SL7 仅生成 GT。
2. 所有模型使用同一 features_v3、模型参数、walk-forward 折和 purge/embargo。
3. v3_n2 基线仍用时间标签训练，但统一按空间 GT 评价，避免各说各话。
4. 价格质量权重只参与训练损失，不得进入推理特征。

用法：
  python -m ml.research.eval_spatial_gt
  python -m ml.research.eval_spatial_gt --pcts 0.006 0.008 0.010 --lambdas 0 0.25 0.5
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from xgboost import XGBClassifier

from ml import features_v3
from ml.labeling import (
    build_sl_price_gt,
    create_labels_sl_proximity,
    generate_nday_signals,
    load_spy,
)
from ml.train_export import _make_model
from ml.walk_forward import (
    make_expanding_folds,
    purge_embargo_mask,
    uniqueness_weights,
)
from ml.versions import VERSIONS
from src.indicators import detect_swing_lows

ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = ROOT / "output"
MODELS_DIR = ROOT / "models"
DATA_DIR = ROOT / "data"
HORIZON_DAYS = 28
DEV_START = "2005-01-01"
DEV_END = "2019-12-31"
FINAL_START = "2020-01-01"
FINAL_END = "2026-12-31"


def _build_base_data():
    """构造共同候选池、特征与时间标签基线。"""
    spy = load_spy().reset_index(drop=True)
    signal = generate_nday_signals(spy, n=2)
    temporal = create_labels_sl_proximity(spy, signal, sl_n=7, k=2)
    feature_data, feature_cols = features_v3.build_features(temporal, spy)
    data = feature_data.dropna(subset=feature_cols).reset_index(drop=True)
    data = data.rename(columns={"label": "temporal_label"})
    position_map = dict(zip(spy["date"], spy.index))
    data["spy_idx"] = data["date"].map(position_map).astype(int)
    return spy, signal, data, feature_cols


def _spatial_target(spy, data, pct):
    gt = build_sl_price_gt(spy, sl_n=7, pct=pct)
    indices = data["spy_idx"].to_numpy()
    y = gt.loc[indices, "is_sl_price_gt"].astype(int).to_numpy()
    premium = gt.loc[indices, "sl_price_premium"].to_numpy(float)
    quality = gt.loc[indices, "price_quality"].to_numpy(float)
    return y, premium, quality, gt


def _price_weights(y, quality, price_lambda):
    """正例内部重排权重，归一化后不改变正例总体损失规模。"""
    weights = np.ones(len(y), dtype=float)
    positive = y == 1
    if price_lambda > 0 and positive.any():
        weights[positive] = 1 + price_lambda * quality[positive]
        weights[positive] /= weights[positive].mean()
    return weights


def _walk_forward_predict(
    X,
    y,
    dates,
    folds,
    model_cfg,
    quality=None,
    price_lambda=0.0,
):
    prediction = np.full(len(y), np.nan)
    passed = np.zeros(len(y), dtype=bool)
    fold_ids = np.full(len(y), -1, dtype=int)
    fold_thresholds = np.full(len(y), np.nan)

    for fold_id, (train_idx, test_idx) in enumerate(folds):
        keep = np.asarray(
            purge_embargo_mask(
                dates.iloc[train_idx],
                dates.iloc[test_idx],
                HORIZON_DAYS,
            )
        )
        train = train_idx[keep]
        if len(train) < 10 or len(np.unique(y[train])) < 2:
            continue

        weights = uniqueness_weights(dates.iloc[train], HORIZON_DAYS)
        if quality is not None and price_lambda > 0:
            weights *= _price_weights(
                y[train],
                quality[train],
                price_lambda,
            )

        model = _make_model(model_cfg)
        model.fit(X[train], y[train], sample_weight=weights)
        test_probability = model.predict_proba(X[test_idx])[:, 1]

        # 沿用现有 walk-forward 的训练集概率中位数阈值，保证横向一致。
        train_probability = model.predict_proba(X[train])[:, 1]
        threshold = float(np.median(train_probability))
        prediction[test_idx] = test_probability
        passed[test_idx] = test_probability >= threshold
        fold_ids[test_idx] = fold_id
        fold_thresholds[test_idx] = threshold

    return pd.DataFrame({
        "proba": prediction,
        "passed": passed,
        "fold_id": fold_ids,
        "fold_threshold": fold_thresholds,
    })


def _sl_centers(spy, sl_n=7):
    """返回 SL 中心在 SPY 全量序列中的位置。"""
    close = spy["close"].to_numpy(float)
    date_strings = spy["date"].dt.strftime("%Y-%m-%d").tolist()
    swing_lows = detect_swing_lows(close.tolist(), date_strings, sl_n)
    swing_low_dates = {item["date"] for item in swing_lows}
    return np.array(
        [i for i, date_str in enumerate(date_strings) if date_str in swing_low_dates],
        dtype=int,
    )


def _event_members(spy, pct):
    """返回每个 SL7 中心对应的空间 GT 交易日集合。"""
    close = spy["close"].to_numpy(float)
    centers = _sl_centers(spy, sl_n=7)
    members = {}
    for center in centers:
        bars = np.arange(max(0, center - 7), min(len(spy), center + 8))
        premium = close[bars] / close[center] - 1
        members[center] = bars[premium <= pct]
    return centers, members


def _event_recall(centers, members, accepted):
    if len(centers) == 0:
        return float("nan")
    accepted = set(int(value) for value in accepted)
    hit = sum(
        any(int(index) in accepted for index in members[center])
        for center in centers
    )
    return hit / len(centers)


def _score_variant(
    y,
    premium,
    result,
    data,
    centers,
    members,
    evaluation_mask=None,
):
    valid = result["proba"].notna().to_numpy(copy=True)
    if evaluation_mask is not None:
        valid &= np.asarray(evaluation_mask, dtype=bool)
    y_valid = y[valid]
    probability = result.loc[valid, "proba"].to_numpy()
    passed = result.loc[valid, "passed"].to_numpy(bool)
    spy_indices = data.loc[valid, "spy_idx"].to_numpy(int)

    start, end = spy_indices.min(), spy_indices.max()
    period_centers = centers[(centers >= start) & (centers <= end)]
    accepted_positive = spy_indices[passed & (y_valid == 1)]
    selected_premium = premium[valid][passed & (y_valid == 1)]

    return {
        "oos_samples": int(valid.sum()),
        "positive_rate": float(y_valid.mean()),
        "auc_roc": float(roc_auc_score(y_valid, probability)),
        "auc_pr": float(average_precision_score(y_valid, probability)),
        "precision": float(precision_score(y_valid, passed, zero_division=0)),
        "recall": float(recall_score(y_valid, passed, zero_division=0)),
        "event_recall": float(
            _event_recall(period_centers, members, accepted_positive)
        ),
        "selected_premium_median": float(np.nanmedian(selected_premium)),
        "selected_count": int(passed.sum()),
    }


def _variant_name(pct, price_lambda):
    pct_bps = int(round(pct * 10_000))
    lambda_tag = int(round(price_lambda * 100))
    return f"spatial_p{pct_bps:04d}_l{lambda_tag:03d}"


def _period_mask(dates, common_mask, start, end):
    return (
        np.asarray(common_mask, dtype=bool)
        & (dates >= pd.Timestamp(start)).to_numpy()
        & (dates <= pd.Timestamp(end)).to_numpy()
    )


def _centered_overpay(spy, data, radius=7):
    """
    计算每个候选日相对前后 radius 根内最低收盘价的多付比例。

    该指标不依赖标签阈值 pct，可用于不同标签模型的统一价格尺子。
    """
    close = spy["close"].to_numpy(float)
    spy_indices = data["spy_idx"].to_numpy(int)
    local_minimum = np.array([
        close[max(0, index - radius):min(len(close), index + radius + 1)].min()
        for index in spy_indices
    ])
    return close[spy_indices] / local_minimum - 1


def _summarize_overpay(values):
    values = np.asarray(values, dtype=float)
    return {
        "overpay_mean": float(np.mean(values)),
        "overpay_median": float(np.median(values)),
        "overpay_p75": float(np.quantile(values, 0.75)),
        "overpay_p90": float(np.quantile(values, 0.90)),
        "within_0_8pct_rate": float(np.mean(values <= 0.008)),
        "exact_bottom_rate": float(np.mean(np.isclose(values, 0.0, atol=1e-12))),
    }


def _matched_budget_rows(
    spy,
    data,
    dates,
    common_mask,
    results,
    variant_meta,
    periods,
):
    """
    以历史 v3_n2 的阈值购买次数作为预算，各模型在同一候选池取 Top-K。

    多付比例以候选日前后 7 根 K 线的最低收盘价为基准。该口径覆盖所有
    被选交易，不会因为某笔交易不属于空间 GT 正例而被静默丢弃。
    """
    overpay = _centered_overpay(spy, data, radius=7)
    baseline = results["v3_n2_stored_oos"]
    rows = []

    for period, start, end in periods:
        mask = _period_mask(dates, common_mask, start, end)
        positions = np.flatnonzero(mask)
        budget = int(baseline.loc[mask, "passed"].sum())
        if budget == 0:
            continue

        for variant, result in results.items():
            probability = result.loc[mask, "proba"].to_numpy(float)
            order = np.argsort(-probability, kind="stable")[:budget]
            selected = positions[order]
            rows.append({
                "comparison": "matched_budget",
                "period": period,
                "variant": variant,
                "pct": variant_meta[variant]["pct"],
                "price_lambda": variant_meta[variant]["price_lambda"],
                "candidate_count": int(mask.sum()),
                "selected_count": budget,
                "event_count": np.nan,
                "covered_event_count": np.nan,
                "stage1_event_coverage": np.nan,
                "post_bottom_rate": np.nan,
                "center_day_rate": np.nan,
                **_summarize_overpay(overpay[selected]),
            })

    return rows


def _event_top1_selections(
    spy,
    data,
    result,
    common_mask,
    start,
    end,
    sl_n=7,
):
    """
    在每个 SL 事件的自然窗口中选择模型分数最高的一个 NDay2 候选日。

    这是事后排序诊断，不是可直接交易的事件识别器。它固定每个事件只买
    一次，用于回答“模型在同一底部附近更愿意买哪一天”。
    """
    close = spy["close"].to_numpy(float)
    spy_indices = data["spy_idx"].to_numpy(int)
    centers = _sl_centers(spy, sl_n=sl_n)

    start_positions = spy.index[spy["date"] >= pd.Timestamp(start)]
    end_positions = spy.index[spy["date"] <= pd.Timestamp(end)]
    if len(start_positions) == 0 or len(end_positions) == 0:
        return pd.DataFrame(), 0

    common_positions = np.flatnonzero(common_mask)
    if len(common_positions) == 0:
        return pd.DataFrame(), 0

    start_index = max(int(start_positions.min()), int(spy_indices[common_positions].min()))
    end_index = min(int(end_positions.max()), int(spy_indices[common_positions].max()))
    period_centers = centers[
        (centers - sl_n >= start_index)
        & (centers + sl_n <= end_index)
    ]

    rows = []
    for center in period_centers:
        candidates = np.flatnonzero(
            np.asarray(common_mask, dtype=bool)
            & (spy_indices >= center - sl_n)
            & (spy_indices <= center + sl_n)
        )
        if len(candidates) == 0:
            continue

        probability = result.loc[candidates, "proba"].to_numpy(float)
        selected = int(candidates[np.argmax(probability)])
        selected_spy_index = int(spy_indices[selected])
        rows.append({
            "event_date": spy.iloc[center]["date"],
            "event_year": int(spy.iloc[center]["date"].year),
            "buy_date": data.iloc[selected]["date"],
            "probability": float(result.loc[selected, "proba"]),
            "overpay": float(close[selected_spy_index] / close[center] - 1),
            "bar_offset": selected_spy_index - int(center),
        })

    return pd.DataFrame(rows), int(len(period_centers))


def _event_top1_rows(
    spy,
    data,
    common_mask,
    results,
    variant_meta,
    periods,
):
    rows = []
    selections = []
    candidate_dates = pd.to_datetime(data["date"])

    for period, start, end in periods:
        period_candidate_count = int(
            _period_mask(
                candidate_dates,
                common_mask,
                start,
                end,
            ).sum()
        )
        for variant, result in results.items():
            selected, event_count = _event_top1_selections(
                spy,
                data,
                result,
                common_mask,
                start,
                end,
            )
            if selected.empty:
                continue
            selected.insert(0, "variant", variant)
            selected.insert(0, "period", period)
            selections.append(selected)

            rows.append({
                "comparison": "event_top1",
                "period": period,
                "variant": variant,
                "pct": variant_meta[variant]["pct"],
                "price_lambda": variant_meta[variant]["price_lambda"],
                "candidate_count": period_candidate_count,
                "selected_count": int(len(selected)),
                "event_count": event_count,
                "covered_event_count": int(len(selected)),
                "stage1_event_coverage": float(len(selected) / event_count),
                "post_bottom_rate": float((selected["bar_offset"] > 0).mean()),
                "center_day_rate": float((selected["bar_offset"] == 0).mean()),
                **_summarize_overpay(selected["overpay"]),
            })

    detail = pd.concat(selections, ignore_index=True) if selections else pd.DataFrame()
    return rows, detail


def _year_block_bootstrap(
    baseline,
    challenger,
    metric,
    n_bootstrap=2_000,
    seed=42,
):
    """按年份成块重采样事件，返回 challenger - baseline 的区间。"""
    paired = baseline.merge(
        challenger,
        on=["event_date", "event_year"],
        suffixes=("_baseline", "_challenger"),
    )
    years = np.array(sorted(paired["event_year"].unique()))
    rng = np.random.default_rng(seed)
    deltas = []

    for _ in range(n_bootstrap):
        sampled_years = rng.choice(years, size=len(years), replace=True)
        sampled = pd.concat(
            [paired[paired["event_year"] == year] for year in sampled_years],
            ignore_index=True,
        )
        baseline_values = sampled["overpay_baseline"].to_numpy(float)
        challenger_values = sampled["overpay_challenger"].to_numpy(float)
        if metric == "median":
            delta = np.median(challenger_values) - np.median(baseline_values)
        elif metric == "mean":
            delta = np.mean(challenger_values) - np.mean(baseline_values)
        elif metric == "within_0_8pct_rate":
            delta = (
                np.mean(challenger_values <= 0.008)
                - np.mean(baseline_values <= 0.008)
            )
        else:
            raise ValueError(f"不支持的 bootstrap 指标: {metric}")
        deltas.append(float(delta))

    deltas = np.asarray(deltas)
    return {
        "estimate": float(
            {
                "median": (
                    np.median(paired["overpay_challenger"])
                    - np.median(paired["overpay_baseline"])
                ),
                "mean": (
                    paired["overpay_challenger"].mean()
                    - paired["overpay_baseline"].mean()
                ),
                "within_0_8pct_rate": (
                    (paired["overpay_challenger"] <= 0.008).mean()
                    - (paired["overpay_baseline"] <= 0.008).mean()
                ),
            }[metric]
        ),
        "ci_low": float(np.quantile(deltas, 0.025)),
        "ci_high": float(np.quantile(deltas, 0.975)),
        "samples": int(len(paired)),
        "blocks": int(len(years)),
    }


def _metric_value(values, metric):
    values = np.asarray(values, dtype=float)
    if metric == "median":
        return float(np.median(values))
    if metric == "mean":
        return float(np.mean(values))
    if metric == "p90":
        return float(np.quantile(values, 0.90))
    if metric == "within_0_8pct_rate":
        return float(np.mean(values <= 0.008))
    raise ValueError(f"不支持的多付比例指标: {metric}")


def _matched_budget_bootstrap(
    spy,
    data,
    dates,
    common_mask,
    baseline,
    challenger,
    metric,
    n_bootstrap=2_000,
    seed=42,
):
    """按年份成块重采样候选日，并在每次重采样中重新执行等预算 Top-K。"""
    mask = _period_mask(dates, common_mask, FINAL_START, FINAL_END)
    positions = np.flatnonzero(mask)
    budget = int(baseline.loc[mask, "passed"].sum())
    budget_rate = budget / len(positions)
    overpay = _centered_overpay(spy, data, radius=7)
    frame = pd.DataFrame({
        "year": dates.iloc[positions].dt.year.to_numpy(int),
        "overpay": overpay[positions],
        "baseline_probability": baseline.loc[mask, "proba"].to_numpy(float),
        "challenger_probability": challenger.loc[mask, "proba"].to_numpy(float),
    })

    def score(sample):
        selected_count = max(1, int(round(len(sample) * budget_rate)))
        baseline_order = np.argsort(
            -sample["baseline_probability"].to_numpy(float),
            kind="stable",
        )[:selected_count]
        challenger_order = np.argsort(
            -sample["challenger_probability"].to_numpy(float),
            kind="stable",
        )[:selected_count]
        baseline_value = _metric_value(
            sample.iloc[baseline_order]["overpay"],
            metric,
        )
        challenger_value = _metric_value(
            sample.iloc[challenger_order]["overpay"],
            metric,
        )
        return challenger_value - baseline_value

    years = np.array(sorted(frame["year"].unique()))
    rng = np.random.default_rng(seed)
    deltas = []
    for _ in range(n_bootstrap):
        sampled_years = rng.choice(years, size=len(years), replace=True)
        sampled = pd.concat(
            [frame[frame["year"] == year] for year in sampled_years],
            ignore_index=True,
        )
        deltas.append(score(sampled))

    deltas = np.asarray(deltas)
    return {
        "estimate": float(score(frame)),
        "ci_low": float(np.quantile(deltas, 0.025)),
        "ci_high": float(np.quantile(deltas, 0.975)),
        "samples": int(len(frame)),
        "blocks": int(len(years)),
    }


def _classification_year_bootstrap(
    y,
    dates,
    evaluation_mask,
    baseline,
    challenger,
    metric,
    n_bootstrap=2_000,
    seed=42,
):
    """按年份成块重采样候选日，比较两组 OOS 概率的分类指标。"""
    positions = np.flatnonzero(evaluation_mask)
    frame = pd.DataFrame({
        "year": dates.iloc[positions].dt.year.to_numpy(int),
        "target": np.asarray(y, dtype=int)[positions],
        "baseline_probability": baseline.loc[
            evaluation_mask,
            "proba",
        ].to_numpy(float),
        "challenger_probability": challenger.loc[
            evaluation_mask,
            "proba",
        ].to_numpy(float),
    })

    def score(sample):
        target = sample["target"].to_numpy(int)
        baseline_probability = sample["baseline_probability"].to_numpy(float)
        challenger_probability = sample["challenger_probability"].to_numpy(float)
        if metric == "auc_roc":
            scorer = roc_auc_score
        elif metric == "auc_pr":
            scorer = average_precision_score
        else:
            raise ValueError(f"不支持的分类 bootstrap 指标: {metric}")
        return float(
            scorer(target, challenger_probability)
            - scorer(target, baseline_probability)
        )

    years = np.array(sorted(frame["year"].unique()))
    rng = np.random.default_rng(seed)
    deltas = []
    for _ in range(n_bootstrap):
        sampled_years = rng.choice(years, size=len(years), replace=True)
        sampled = pd.concat(
            [frame[frame["year"] == year] for year in sampled_years],
            ignore_index=True,
        )
        if sampled["target"].nunique() < 2:
            continue
        deltas.append(score(sampled))

    deltas = np.asarray(deltas)
    return {
        "estimate": float(score(frame)),
        "ci_low": float(np.quantile(deltas, 0.025)),
        "ci_high": float(np.quantile(deltas, 0.975)),
        "samples": int(len(frame)),
        "blocks": int(len(years)),
    }


def _semantic_csv_hash(path, cutoff):
    """计算截止指定日期的规范化 CSV 内容哈希，忽略文件末尾后续行情。"""
    frame = pd.read_csv(path)
    date_column = "时间" if "时间" in frame.columns else "date"
    frame[date_column] = pd.to_datetime(frame[date_column])
    prefix = frame[frame[date_column] <= pd.Timestamp(cutoff)].copy()
    prefix[date_column] = prefix[date_column].dt.strftime("%Y-%m-%d")
    payload = prefix.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return {
        "path": str(path.relative_to(ROOT)),
        "rows_through_cutoff": int(len(prefix)),
        "last_date_in_file": frame[date_column].max().strftime("%Y-%m-%d"),
        "sha256_through_cutoff": hashlib.sha256(payload).hexdigest(),
    }


def _first_stage_metrics(spy, signal, gt, centers, members, start, end):
    eligible = (spy.index >= start) & (spy.index <= end)
    candidate = signal.to_numpy(bool) & eligible
    target = gt["is_sl_price_gt"].to_numpy(bool) & eligible
    true_positive = candidate & target
    period_centers = centers[(centers >= start) & (centers <= end)]
    return {
        "stage1_precision": float(true_positive.sum() / candidate.sum()),
        "stage1_day_recall": float(true_positive.sum() / target.sum()),
        "stage1_event_recall": float(
            _event_recall(
                period_centers,
                members,
                np.flatnonzero(true_positive),
            )
        ),
        "gt_days_per_event": float(target.sum() / len(period_centers)),
    }


def _fit_full_model(X, y, dates, model_cfg, quality=None, price_lambda=0.0):
    weights = uniqueness_weights(dates, HORIZON_DAYS)
    if quality is not None and price_lambda > 0:
        weights *= _price_weights(y, quality, price_lambda)
    model = _make_model(model_cfg)
    model.fit(X, y, sample_weight=weights)
    return model


def _load_stored_v3_n2_oos(data):
    """加载仓库已有的 v3_n2 历史样本外预测，并对齐到共同候选池。"""
    path = OUTPUT_DIR / "oos_proba_v3_n2.csv"
    result = pd.DataFrame({
        "proba": np.nan,
        "passed": False,
        "fold_id": -1,
        "fold_threshold": np.nan,
    }, index=data.index)
    if not path.exists():
        return result

    stored = pd.read_csv(path)
    stored["date"] = pd.to_datetime(stored["date"])
    date_to_index = dict(zip(pd.to_datetime(data["date"]), data.index))
    for _, row in stored.iterrows():
        index = date_to_index.get(row["date"])
        if index is None:
            continue
        result.loc[index, "proba"] = row["proba"]
        result.loc[index, "fold_id"] = int(row["fold_id"])
        result.loc[index, "fold_threshold"] = row["fold_threshold"]
        result.loc[index, "passed"] = row["proba"] >= row["fold_threshold"]
    return result


def _frozen_model_comparison(
    spy,
    data,
    feature_cols,
    pct,
    price_lambda,
):
    """用生产模型训练期之后的数据做小样本冻结模型检查。"""
    model_path = MODELS_DIR / "spy_nday2_v3_n2.ubj"
    meta_path = MODELS_DIR / "spy_nday2_v3_n2.json"
    if not model_path.exists() or not meta_path.exists():
        return []

    from xgboost import XGBClassifier

    with open(meta_path, encoding="utf-8") as file:
        meta = json.load(file)
    train_end = pd.Timestamp(meta["train_period"][-1])
    y, premium, quality, _ = _spatial_target(spy, data, pct)
    X = data[feature_cols].to_numpy()
    dates = pd.to_datetime(data["date"])

    # 候选日最多会受未来 7 根后的 SL 中心影响，而该中心还需 7 根确认。
    gt_known = data["spy_idx"].to_numpy() + 14 < len(spy)
    train = (dates <= train_end).to_numpy()
    test = ((dates > train_end).to_numpy()) & gt_known
    if test.sum() < 2 or len(np.unique(y[test])) < 2:
        return []

    frozen = XGBClassifier()
    frozen.load_model(str(model_path))
    spatial = _fit_full_model(
        X[train],
        y[train],
        dates[train],
        VERSIONS["v3_n2"]["model"],
        quality=quality[train],
        price_lambda=price_lambda,
    )

    rows = []
    for name, model in [
        ("deployed_v3_n2", frozen),
        (f"spatial_p{int(round(pct * 10000)):04d}", spatial),
    ]:
        probability = model.predict_proba(X[test])[:, 1]
        passed = probability >= 0.5
        rows.append({
            "variant": name,
            "pct": pct,
            "price_lambda": price_lambda if name.startswith("spatial") else 0.0,
            "test_start": dates[test].min().strftime("%Y-%m-%d"),
            "test_end": dates[test].max().strftime("%Y-%m-%d"),
            "samples": int(test.sum()),
            "small_sample_warning": bool(test.sum() < 30),
            "positive_rate": float(y[test].mean()),
            "auc_roc": float(roc_auc_score(y[test], probability)),
            "auc_pr": float(average_precision_score(y[test], probability)),
            "precision_at_050": float(
                precision_score(y[test], passed, zero_division=0)
            ),
            "recall_at_050": float(
                recall_score(y[test], passed, zero_division=0)
            ),
            "selected_at_050": int(passed.sum()),
            "selected_positive_premium_median": float(
                np.nanmedian(premium[test][passed & (y[test] == 1)])
            ),
        })
    return rows


def run(
    pcts,
    lambdas,
    folds_count=4,
    final_pct=0.008,
    final_lambda=0.25,
    bootstrap_samples=2_000,
):
    spy, signal, data, feature_cols = _build_base_data()
    X = data[feature_cols].to_numpy()
    dates = pd.to_datetime(data["date"])
    temporal_y = data["temporal_label"].astype(int).to_numpy()
    config = VERSIONS["v3_n2"]
    folds = make_expanding_folds(
        dates,
        n_folds=folds_count,
        min_train=max(20, int(len(data) * 0.4)),
    )

    baseline = _walk_forward_predict(
        X,
        temporal_y,
        dates,
        folds,
        config["model"],
    )
    stored_baseline = _load_stored_v3_n2_oos(data)

    results = {
        "v3_n2_temporal": baseline,
        "v3_n2_stored_oos": stored_baseline,
    }
    variant_meta = {
        "v3_n2_temporal": {"pct": np.nan, "price_lambda": 0.0},
        "v3_n2_stored_oos": {"pct": np.nan, "price_lambda": 0.0},
    }
    spatial_targets = {}

    for pct in pcts:
        y, premium, quality, gt = _spatial_target(spy, data, pct)
        centers, members = _event_members(spy, pct)
        spatial_targets[pct] = {
            "y": y,
            "premium": premium,
            "quality": quality,
            "gt": gt,
            "centers": centers,
            "members": members,
        }
        for price_lambda in lambdas:
            variant = _variant_name(pct, price_lambda)
            results[variant] = _walk_forward_predict(
                X,
                y,
                dates,
                folds,
                config["model"],
                quality=quality,
                price_lambda=price_lambda,
            )
            variant_meta[variant] = {
                "pct": pct,
                "price_lambda": price_lambda,
            }

    common_mask = (
        baseline["proba"].notna().to_numpy()
        & stored_baseline["proba"].notna().to_numpy()
    )
    for variant, result in results.items():
        if variant.startswith("spatial_"):
            common_mask &= result["proba"].notna().to_numpy()
    if not common_mask.any():
        raise RuntimeError("没有可用于公平对比的共同样本外候选日")

    comparison_rows = []
    period_rows = []
    frozen_rows = []

    for pct in pcts:
        target = spatial_targets[pct]
        y = target["y"]
        premium = target["premium"]
        gt = target["gt"]
        centers = target["centers"]
        members = target["members"]
        spy_indices = data.loc[common_mask, "spy_idx"].to_numpy(int)
        first_stage = _first_stage_metrics(
            spy,
            signal,
            gt,
            centers,
            members,
            int(spy_indices.min()),
            int(spy_indices.max()),
        )

        baseline_score = _score_variant(
            y,
            premium,
            baseline,
            data,
            centers,
            members,
            evaluation_mask=common_mask,
        )
        comparison_rows.append({
            "variant": "v3_n2_temporal",
            "pct": pct,
            "price_lambda": 0.0,
            **first_stage,
            **baseline_score,
        })
        if stored_baseline["proba"].notna().any():
            stored_score = _score_variant(
                y,
                premium,
                stored_baseline,
                data,
                centers,
                members,
                evaluation_mask=common_mask,
            )
            comparison_rows.append({
                "variant": "v3_n2_stored_oos",
                "pct": pct,
                "price_lambda": 0.0,
                **first_stage,
                **stored_score,
            })

        for price_lambda in lambdas:
            variant = _variant_name(pct, price_lambda)
            result = results[variant]
            score = _score_variant(
                y,
                premium,
                result,
                data,
                centers,
                members,
                evaluation_mask=common_mask,
            )
            comparison_rows.append({
                "variant": "spatial",
                "pct": pct,
                "price_lambda": price_lambda,
                **first_stage,
                **score,
            })

            for period, start, end in [
                ("2005-2012", "2005-01-01", "2012-12-31"),
                ("2013-2019", "2013-01-01", "2019-12-31"),
                ("2020-2026", "2020-01-01", "2026-12-31"),
            ]:
                mask = _period_mask(dates, common_mask, start, end)
                if mask.sum() < 20 or len(np.unique(y[mask])) < 2:
                    continue
                passed = result.loc[mask, "passed"].to_numpy(bool)
                period_rows.append({
                    "pct": pct,
                    "price_lambda": price_lambda,
                    "period": period,
                    "samples": int(mask.sum()),
                    "auc_roc": float(
                        roc_auc_score(y[mask], result.loc[mask, "proba"])
                    ),
                    "auc_pr": float(
                        average_precision_score(
                            y[mask],
                            result.loc[mask, "proba"],
                        )
                    ),
                    "precision": float(
                        precision_score(y[mask], passed, zero_division=0)
                    ),
                    "recall": float(
                        recall_score(y[mask], passed, zero_division=0)
                    ),
                })

        frozen_rows.extend(
            _frozen_model_comparison(
                spy,
                data,
                feature_cols,
                pct,
                price_lambda=final_lambda,
            )
        )

    comparison = pd.DataFrame(comparison_rows)
    periods = pd.DataFrame(period_rows)
    frozen = pd.DataFrame(frozen_rows)
    evaluation_periods = [
        ("development", DEV_START, DEV_END),
        ("final_test", FINAL_START, FINAL_END),
        ("all_common_oos", DEV_START, FINAL_END),
    ]
    overpay_rows = _matched_budget_rows(
        spy,
        data,
        dates,
        common_mask,
        results,
        variant_meta,
        evaluation_periods,
    )
    event_rows, event_detail = _event_top1_rows(
        spy,
        data,
        common_mask,
        results,
        variant_meta,
        evaluation_periods,
    )
    overpay = pd.DataFrame(overpay_rows + event_rows)

    final_variant = _variant_name(final_pct, final_lambda)
    if final_variant not in results:
        raise ValueError(
            "最终候选参数必须包含在 --pcts 与 --lambdas 的遍历范围中: "
            f"{final_variant}"
        )
    final_target_key = next(
        pct for pct in spatial_targets
        if np.isclose(pct, final_pct)
    )
    final_target = spatial_targets[final_target_key]["y"]
    final_baseline_events = event_detail[
        (event_detail["period"] == "final_test")
        & (event_detail["variant"] == "v3_n2_stored_oos")
    ]
    final_challenger_events = event_detail[
        (event_detail["period"] == "final_test")
        & (event_detail["variant"] == final_variant)
    ]
    bootstrap_rows = []
    for metric in ["median", "mean", "within_0_8pct_rate"]:
        result = _year_block_bootstrap(
            final_baseline_events,
            final_challenger_events,
            metric,
            n_bootstrap=bootstrap_samples,
        )
        bootstrap_rows.append({
            "comparison": "event_top1",
            "period": "final_test",
            "baseline": "v3_n2_stored_oos",
            "challenger": final_variant,
            "metric": metric,
            **result,
        })
    for metric in ["median", "mean", "p90", "within_0_8pct_rate"]:
        result = _matched_budget_bootstrap(
            spy,
            data,
            dates,
            common_mask,
            stored_baseline,
            results[final_variant],
            metric,
            n_bootstrap=bootstrap_samples,
        )
        bootstrap_rows.append({
            "comparison": "matched_budget",
            "period": "final_test",
            "baseline": "v3_n2_stored_oos",
            "challenger": final_variant,
            "metric": metric,
            **result,
        })
    for period, mask in [
        ("all_common_oos", common_mask),
        (
            "final_test",
            _period_mask(
                dates,
                common_mask,
                FINAL_START,
                FINAL_END,
            ),
        ),
    ]:
        for metric in ["auc_roc", "auc_pr"]:
            result = _classification_year_bootstrap(
                final_target,
                dates,
                mask,
                stored_baseline,
                results[final_variant],
                metric,
                n_bootstrap=bootstrap_samples,
            )
            bootstrap_rows.append({
                "comparison": "classification",
                "period": period,
                "baseline": "v3_n2_stored_oos",
                "challenger": final_variant,
                "metric": metric,
                **result,
            })
    bootstrap = pd.DataFrame(bootstrap_rows)
    event_detail_export = event_detail[
        event_detail["variant"].isin([
            "v3_n2_stored_oos",
            final_variant,
        ])
    ].copy()
    common_dates = dates[common_mask]
    common_end = common_dates.max().strftime("%Y-%m-%d")
    run_meta = {
        "purpose": "空间 GT 参数遍历与 v3_n2 公平对比",
        "pcts": [float(value) for value in pcts],
        "price_lambdas": [float(value) for value in lambdas],
        "folds": int(folds_count),
        "horizon_days": HORIZON_DAYS,
        "development_period": [DEV_START, DEV_END],
        "final_test_period": [FINAL_START, common_end],
        "common_oos_samples": int(common_mask.sum()),
        "common_oos_period": [
            common_dates.min().strftime("%Y-%m-%d"),
            common_end,
        ],
        "final_variant": final_variant,
        "final_pct": float(final_pct),
        "final_price_lambda": float(final_lambda),
        "model_config": config["model"],
        "data_snapshot": [
            _semantic_csv_hash(DATA_DIR / filename, common_end)
            for filename in [
                "SPY_adjusted.csv",
                "sp500_breadth.csv",
                "vix_daily.csv",
            ]
        ],
        "notes": [
            "主对比只使用与仓库历史 v3_n2 OOS 文件重合的候选日。",
            "数据哈希仅覆盖共同 OOS 截止日，文件末尾的新行情不影响主对比。",
            "冻结上线模型比较使用截止当前文件末尾的数据，且样本量过小。",
        ],
    }

    OUTPUT_DIR.mkdir(exist_ok=True)
    comparison_path = OUTPUT_DIR / "spatial_gt_comparison.csv"
    periods_path = OUTPUT_DIR / "spatial_gt_periods.csv"
    frozen_path = OUTPUT_DIR / "spatial_gt_frozen_comparison.csv"
    overpay_path = OUTPUT_DIR / "spatial_gt_overpay.csv"
    event_detail_path = OUTPUT_DIR / "spatial_gt_event_selections.csv"
    bootstrap_path = OUTPUT_DIR / "spatial_gt_bootstrap.csv"
    run_meta_path = OUTPUT_DIR / "spatial_gt_run_meta.json"
    comparison.to_csv(comparison_path, index=False)
    periods.to_csv(periods_path, index=False)
    frozen.to_csv(frozen_path, index=False)
    overpay.to_csv(overpay_path, index=False)
    event_detail_export.to_csv(event_detail_path, index=False)
    bootstrap.to_csv(bootstrap_path, index=False)
    with open(run_meta_path, "w", encoding="utf-8") as file:
        json.dump(run_meta, file, ensure_ascii=False, indent=2)

    print("\n[共同空间 GT：v3_n2 基线 vs 空间标签]")
    columns = [
        "variant",
        "pct",
        "price_lambda",
        "auc_roc",
        "auc_pr",
        "precision",
        "recall",
        "event_recall",
        "selected_premium_median",
    ]
    print(comparison[columns].to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    final_overpay = overpay[
        (overpay["period"] == "final_test")
        & overpay["variant"].isin(["v3_n2_stored_oos", final_variant])
    ]
    print("\n[最终测试：统一离底溢价尺子]")
    overpay_columns = [
        "comparison",
        "variant",
        "selected_count",
        "overpay_median",
        "overpay_mean",
        "overpay_p90",
        "within_0_8pct_rate",
        "center_day_rate",
        "post_bottom_rate",
    ]
    print(
        final_overpay[overpay_columns].to_string(
            index=False,
            float_format=lambda x: f"{x:.4f}",
        )
    )
    print(f"\n[Output] {comparison_path}")
    print(f"[Output] {periods_path}")
    print(f"[Output] {frozen_path}")
    print(f"[Output] {overpay_path}")
    print(f"[Output] {event_detail_path}")
    print(f"[Output] {bootstrap_path}")
    print(f"[Output] {run_meta_path}")
    return {
        "comparison": comparison,
        "periods": periods,
        "frozen": frozen,
        "overpay": overpay,
        "event_detail": event_detail,
        "bootstrap": bootstrap,
    }


def main():
    parser = argparse.ArgumentParser(description="空间 GT 参数遍历与消融评估")
    parser.add_argument(
        "--pcts",
        type=float,
        nargs="+",
        default=[0.006, 0.008, 0.010],
    )
    parser.add_argument(
        "--lambdas",
        type=float,
        nargs="+",
        default=[0.0, 0.25, 0.5],
    )
    parser.add_argument("--folds", type=int, default=4)
    parser.add_argument("--final-pct", type=float, default=0.008)
    parser.add_argument("--final-lambda", type=float, default=0.25)
    parser.add_argument("--bootstrap-samples", type=int, default=2_000)
    args = parser.parse_args()
    run(
        tuple(args.pcts),
        tuple(args.lambdas),
        folds_count=args.folds,
        final_pct=args.final_pct,
        final_lambda=args.final_lambda,
        bootstrap_samples=args.bootstrap_samples,
    )


if __name__ == "__main__":
    main()
