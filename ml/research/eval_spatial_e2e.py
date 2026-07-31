"""
空间 GT 模型的因果端到端评估。

本脚本只用于研究，不导出模型、不修改版本注册表。与事后 Top-K 不同：

1. 仅使用 2005-2019 开发段校准放行率；
2. 2020 年后的阈值规则冻结，不读取测试段目标；
3. 信号日在收盘后形成，统一在下一交易日开盘执行；
4. 同时报告两阶段检测质量、实际成交价格质量和标准化执行层结果。
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from experiments.configs import DATA_FILE, FEE_RATE, SMH_FILE
from ml.research.eval_spatial_gt import (
    HORIZON_DAYS,
    _build_base_data,
    _event_members,
    _event_recall,
    _load_stored_v3_n2_oos,
    _price_weights,
    _spatial_target,
)
from ml.train_export import _make_model
from ml.versions import VERSIONS
from ml.walk_forward import (
    make_expanding_folds,
    purge_embargo_mask,
    uniqueness_weights,
)
from src.backtest_engine import BacktestEngine
from src.data_loader import load_data
from src.modules.entry import OOSProbaEntry
from src.modules.position import FixedPyramid
from src.modules.take_profit import NoTakeProfit
from src.modules.tiers import FixedTiers
from src.strategies.composable import ComposableStrategy

ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = ROOT / "output"
DEV_START = pd.Timestamp("2005-01-01")
DEV_END = pd.Timestamp("2019-12-31")
FINAL_START = pd.Timestamp("2020-01-01")
FINAL_PCT = 0.008
FINAL_LAMBDA = 0.25


def _walk_forward_rank(
    X,
    y,
    dates,
    folds,
    model_cfg,
    quality=None,
    price_lambda=0.0,
):
    """生成样本外概率和相对本折训练概率的因果分位排名。"""
    probability = np.full(len(y), np.nan)
    train_percentile = np.full(len(y), np.nan)
    fold_ids = np.full(len(y), -1, dtype=int)

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
        train_probability = np.sort(model.predict_proba(X[train])[:, 1])
        test_probability = model.predict_proba(X[test_idx])[:, 1]

        probability[test_idx] = test_probability
        train_percentile[test_idx] = (
            np.searchsorted(
                train_probability,
                test_probability,
                side="right",
            )
            / len(train_probability)
        )
        fold_ids[test_idx] = fold_id

    return pd.DataFrame({
        "proba": probability,
        "train_percentile": train_percentile,
        "fold_id": fold_ids,
    })


def _calibrate_rank_threshold(scores, mask, target_rate):
    """在开发段选择最接近目标放行率的训练分位阈值。"""
    values = np.asarray(scores[mask], dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        raise ValueError("开发段没有可用于阈值校准的分数")

    candidates = np.unique(values)
    rates = np.array([(values >= value).mean() for value in candidates])
    best = int(np.argmin(np.abs(rates - target_rate)))
    return float(candidates[best]), float(rates[best])


def _xirr(cashflows):
    """计算不规则现金流年化收益率。"""
    if len(cashflows) < 2:
        return float("nan")
    start = min(date for date, _ in cashflows)

    def npv(rate):
        return sum(
            amount / ((1 + rate) ** ((date - start).days / 365.0))
            for date, amount in cashflows
        )

    low = -0.9999
    high = 10.0
    low_value = npv(low)
    high_value = npv(high)
    while low_value * high_value > 0 and high < 1_000_000:
        high *= 10
        high_value = npv(high)
    if low_value * high_value > 0:
        return float("nan")
    return float(brentq(npv, low, high, maxiter=1_000))


def _candidate_execution_frame(spy, data, final_mask):
    """为测试段每个候选日预先计算下一开盘成交质量。"""
    spy_dates = pd.to_datetime(spy["date"]).reset_index(drop=True)
    open_prices = spy["open"].astype(float).to_numpy()
    close_prices = spy["close"].astype(float).to_numpy()
    low_prices = spy["low"].astype(float).to_numpy()
    final_end = pd.to_datetime(data.loc[final_mask, "date"]).max()
    final_end_idx = int(spy_dates[spy_dates <= final_end].index.max())

    rows = []
    for data_idx in np.flatnonzero(final_mask):
        decision_idx = int(data.iloc[data_idx]["spy_idx"])
        execution_idx = decision_idx + 1
        if execution_idx > final_end_idx:
            continue

        start = max(0, execution_idx - 7)
        end = min(len(spy), execution_idx + 8)
        entry = float(open_prices[execution_idx])
        local_min_open = float(open_prices[start:end].min())

        row = {
            "data_idx": int(data_idx),
            "decision_date": pd.Timestamp(data.iloc[data_idx]["date"]),
            "execution_date": pd.Timestamp(spy_dates.iloc[execution_idx]),
            "entry_open": entry,
            "execution_overpay": entry / local_min_open - 1,
            "mae_20d": np.nan,
        }
        for horizon in [20, 60, 120, 252]:
            row[f"gross_return_{horizon}d"] = np.nan
            row[f"net_return_{horizon}d"] = np.nan

        end_20 = execution_idx + 20
        if end_20 < len(spy):
            row["mae_20d"] = (
                float(low_prices[execution_idx:end_20 + 1].min()) / entry - 1
            )
        for horizon in [20, 60, 120, 252]:
            end_horizon = execution_idx + horizon
            if end_horizon >= len(spy):
                continue
            row[f"gross_return_{horizon}d"] = float(
                close_prices[end_horizon] / entry - 1
            )
            row[f"net_return_{horizon}d"] = float(
                close_prices[end_horizon] * (1 - FEE_RATE)
                / (entry * (1 + FEE_RATE))
                - 1
            )
        rows.append(row)

    return pd.DataFrame(rows), final_end, final_end_idx


def _signal_metrics(
    spy,
    data,
    gt,
    centers,
    members,
    final_mask,
    selected_mask,
):
    """计算从全市场 GT 到最终放行日的两阶段端到端指标。"""
    selected = np.asarray(selected_mask, dtype=bool) & final_mask
    candidate_indices = data.loc[final_mask, "spy_idx"].to_numpy(int)
    selected_indices = data.loc[selected, "spy_idx"].to_numpy(int)
    candidate_positive = gt.loc[
        candidate_indices,
        "is_sl_price_gt",
    ].to_numpy(bool)
    selected_positive = gt.loc[
        selected_indices,
        "is_sl_price_gt",
    ].to_numpy(bool)

    start_idx = int(candidate_indices.min())
    end_idx = int(candidate_indices.max())
    eligible = (spy.index >= start_idx) & (spy.index <= end_idx)
    target = gt["is_sl_price_gt"].to_numpy(bool) & eligible
    period_centers = centers[
        (centers >= start_idx)
        & (centers <= end_idx)
    ]
    accepted_positive = selected_indices[selected_positive]

    def window_recall(indices):
        accepted = np.asarray(indices, dtype=int)
        if len(period_centers) == 0:
            return float("nan")
        return float(
            np.mean([
                bool(np.any(np.abs(accepted - center) <= 7))
                for center in period_centers
            ])
        )

    return {
        "candidate_count": int(final_mask.sum()),
        "candidate_positive_count": int(candidate_positive.sum()),
        "selected_count": int(selected.sum()),
        "selected_rate": float(selected.sum() / final_mask.sum()),
        "precision": (
            float(selected_positive.mean())
            if len(selected_positive)
            else float("nan")
        ),
        "stage2_candidate_recall": (
            float(selected_positive.sum() / candidate_positive.sum())
            if candidate_positive.sum()
            else float("nan")
        ),
        "end_to_end_day_recall": (
            float(selected_positive.sum() / target.sum())
            if target.sum()
            else float("nan")
        ),
        "stage1_event_recall": float(
            _event_recall(
                period_centers,
                members,
                candidate_indices[candidate_positive],
            )
        ),
        "stage1_event_window_coverage": window_recall(candidate_indices),
        "end_to_end_event_recall": float(
            _event_recall(
                period_centers,
                members,
                accepted_positive,
            )
        ),
        "end_to_end_event_window_coverage": window_recall(selected_indices),
        "event_count": int(len(period_centers)),
    }


def _trade_metrics(detail, spy, final_end_idx):
    """汇总下一开盘成交质量与现金流收益。"""
    if detail.empty:
        return {}

    overpay = detail["execution_overpay"].to_numpy(float)
    final_date = pd.Timestamp(spy.iloc[final_end_idx]["date"])
    final_close = float(spy.iloc[final_end_idx]["close"])
    costs = detail["entry_open"].to_numpy(float) * (1 + FEE_RATE)
    liquidation = len(detail) * final_close * (1 - FEE_RATE)
    cashflows = [
        (pd.Timestamp(row.execution_date), -float(row.entry_open) * (1 + FEE_RATE))
        for row in detail.itertuples()
    ]
    cashflows.append((final_date, liquidation))

    result = {
        "execution_count": int(len(detail)),
        "execution_overpay_median": float(np.median(overpay)),
        "execution_overpay_mean": float(np.mean(overpay)),
        "execution_overpay_p90": float(np.quantile(overpay, 0.90)),
        "execution_within_0_8pct_rate": float(np.mean(overpay <= 0.008)),
        "cashflow_xirr": _xirr(cashflows),
        "liquidation_return_on_cost": float(liquidation / costs.sum() - 1),
    }
    for horizon in [20, 60, 120, 252]:
        values = detail[f"net_return_{horizon}d"].dropna().to_numpy(float)
        result[f"net_return_{horizon}d_count"] = int(len(values))
        result[f"net_return_{horizon}d_mean"] = float(np.mean(values))
        result[f"net_return_{horizon}d_median"] = float(np.median(values))
        result[f"net_return_{horizon}d_hit_rate"] = float(np.mean(values > 0))
    return result


def _run_engine(execution_dates, start, end):
    """使用项目标准化执行层运行下一开盘信号。"""
    data = load_data(str(ROOT / DATA_FILE), start, end)
    smh = load_data(str(ROOT / SMH_FILE), start, end)
    strategy = ComposableStrategy(
        tiers=FixedTiers(drops=(0.0, 0.0, 0.0)),
        entry=OOSProbaEntry(
            pd.to_datetime(execution_dates).dt.strftime("%Y-%m-%d").tolist()
        ),
        position=FixedPyramid(
            market_shares=1,
            limit_shares=(0, 0, 0),
        ),
        take_profit=NoTakeProfit(),
    )
    result = BacktestEngine(data, smh, FEE_RATE, strategy).run()
    return {
        "engine_buy_count": int(result["buy_count"]),
        "engine_total_return": float(result["total_return"]),
        "engine_annualized_return": float(result["annualized_return"]),
        "engine_sharpe": float(result["sharpe_ratio"]),
        "engine_max_drawdown": float(result["max_drawdown"]),
        "engine_calmar": float(result["calmar_ratio"]),
        "engine_cost_advantage": float(result["cost_advantage"]),
    }


def _bootstrap_metric(values, selected, metric):
    chosen = values[selected]
    if len(chosen) == 0:
        return float("nan")
    if metric == "overpay_median":
        return float(np.median(chosen))
    if metric == "overpay_mean":
        return float(np.mean(chosen))
    if metric == "within_0_8pct_rate":
        return float(np.mean(chosen <= 0.008))
    if metric.startswith("net_return_") and metric.endswith("_mean"):
        return float(np.nanmean(chosen))
    if metric.startswith("net_return_") and metric.endswith("_hit_rate"):
        return float(np.nanmean(chosen > 0))
    raise ValueError(f"不支持的 bootstrap 指标: {metric}")


def _year_block_bootstrap(
    candidate_detail,
    baseline_name,
    challenger_name,
    n_bootstrap=2_000,
    seed=42,
):
    """按年份有放回抽样，估计两套在线决策的指标差值。"""
    rng = np.random.default_rng(seed)
    years = np.sort(candidate_detail["year"].unique())
    rows = []

    metric_columns = {
        "overpay_median": "execution_overpay",
        "overpay_mean": "execution_overpay",
        "within_0_8pct_rate": "execution_overpay",
        "net_return_20d_mean": "net_return_20d",
        "net_return_20d_hit_rate": "net_return_20d",
        "net_return_60d_mean": "net_return_60d",
        "net_return_120d_mean": "net_return_120d",
        "net_return_252d_mean": "net_return_252d",
    }
    for metric, value_column in metric_columns.items():
        point_baseline = _bootstrap_metric(
            candidate_detail[value_column].to_numpy(float),
            candidate_detail[baseline_name].to_numpy(bool),
            metric,
        )
        point_challenger = _bootstrap_metric(
            candidate_detail[value_column].to_numpy(float),
            candidate_detail[challenger_name].to_numpy(bool),
            metric,
        )
        differences = []
        for _ in range(n_bootstrap):
            sampled_years = rng.choice(years, size=len(years), replace=True)
            sampled = pd.concat(
                [
                    candidate_detail[candidate_detail["year"] == year]
                    for year in sampled_years
                ],
                ignore_index=True,
            )
            baseline_value = _bootstrap_metric(
                sampled[value_column].to_numpy(float),
                sampled[baseline_name].to_numpy(bool),
                metric,
            )
            challenger_value = _bootstrap_metric(
                sampled[value_column].to_numpy(float),
                sampled[challenger_name].to_numpy(bool),
                metric,
            )
            differences.append(challenger_value - baseline_value)

        rows.append({
            "metric": metric,
            "baseline": baseline_name,
            "challenger": challenger_name,
            "baseline_value": point_baseline,
            "challenger_value": point_challenger,
            "difference": point_challenger - point_baseline,
            "ci_low": float(np.nanquantile(differences, 0.025)),
            "ci_high": float(np.nanquantile(differences, 0.975)),
            "bootstrap_samples": int(n_bootstrap),
        })
    return pd.DataFrame(rows)


def run(n_bootstrap=2_000):
    spy, _, data, feature_cols = _build_base_data()
    X = data[feature_cols].to_numpy()
    dates = pd.to_datetime(data["date"]).reset_index(drop=True)
    temporal_y = data["temporal_label"].astype(int).to_numpy()
    spatial_y, _, quality, gt = _spatial_target(spy, data, FINAL_PCT)
    centers, members = _event_members(spy, FINAL_PCT)
    config = VERSIONS["v3_n2"]
    folds = make_expanding_folds(
        dates,
        n_folds=4,
        min_train=max(20, int(len(data) * 0.4)),
    )

    temporal = _walk_forward_rank(
        X,
        temporal_y,
        dates,
        folds,
        config["model"],
    )
    spatial = _walk_forward_rank(
        X,
        spatial_y,
        dates,
        folds,
        config["model"],
        quality=quality,
        price_lambda=FINAL_LAMBDA,
    )
    stored = _load_stored_v3_n2_oos(data)

    common = (
        temporal["proba"].notna().to_numpy()
        & spatial["proba"].notna().to_numpy()
        & stored["proba"].notna().to_numpy()
    )
    common_end = dates[common].max()
    dev_mask = (
        common
        & (dates >= DEV_START).to_numpy()
        & (dates <= DEV_END).to_numpy()
    )
    final_mask = (
        common
        & (dates >= FINAL_START).to_numpy()
        & (dates <= common_end).to_numpy()
    )

    target_rate = float(stored.loc[dev_mask, "passed"].mean())
    temporal_threshold, temporal_dev_rate = _calibrate_rank_threshold(
        temporal["train_percentile"].to_numpy(float),
        dev_mask,
        target_rate,
    )
    spatial_threshold, spatial_dev_rate = _calibrate_rank_threshold(
        spatial["train_percentile"].to_numpy(float),
        dev_mask,
        target_rate,
    )

    decisions = {
        "stage1_nday2": final_mask.copy(),
        "v3_n2_stored_oos": (
            final_mask & stored["passed"].to_numpy(bool)
        ),
        "v3_n2_temporal_q50": (
            final_mask
            & (
                temporal["train_percentile"].to_numpy(float)
                >= 0.5
            )
        ),
        "spatial_p0080_l025_q50": (
            final_mask
            & (
                spatial["train_percentile"].to_numpy(float)
                >= 0.5
            )
        ),
        "v3_n2_temporal_calibrated": (
            final_mask
            & (
                temporal["train_percentile"].to_numpy(float)
                >= temporal_threshold
            )
        ),
        "spatial_p0080_l025_calibrated": (
            final_mask
            & (
                spatial["train_percentile"].to_numpy(float)
                >= spatial_threshold
            )
        ),
    }

    candidate_execution, final_end, final_end_idx = (
        _candidate_execution_frame(spy, data, final_mask)
    )
    summary_rows = []
    trade_frames = []
    for variant, selected in decisions.items():
        signal_metrics = _signal_metrics(
            spy,
            data,
            gt,
            centers,
            members,
            final_mask,
            selected,
        )
        detail = candidate_execution[
            candidate_execution["data_idx"].isin(np.flatnonzero(selected))
        ].copy()
        detail.insert(0, "variant", variant)
        trade_frames.append(detail)
        trade_metrics = _trade_metrics(detail, spy, final_end_idx)
        engine_metrics = _run_engine(
            detail["execution_date"],
            FINAL_START.strftime("%Y-%m-%d"),
            final_end.strftime("%Y-%m-%d"),
        )
        summary_rows.append({
            "variant": variant,
            "period_start": FINAL_START.strftime("%Y-%m-%d"),
            "period_end": final_end.strftime("%Y-%m-%d"),
            **signal_metrics,
            **trade_metrics,
            **engine_metrics,
        })

    summary = pd.DataFrame(summary_rows)
    trades = pd.concat(trade_frames, ignore_index=True)

    candidate_detail = candidate_execution.copy()
    candidate_detail["year"] = candidate_detail["decision_date"].dt.year
    for horizon in [20, 60, 120, 252]:
        candidate_detail[f"net_return_{horizon}d"] = candidate_detail[
            f"net_return_{horizon}d"
        ].astype(float)
    for name, selected in decisions.items():
        selected_indices = set(np.flatnonzero(selected).tolist())
        candidate_detail[name] = candidate_detail["data_idx"].isin(selected_indices)

    bootstrap = pd.concat(
        [
            _year_block_bootstrap(
                candidate_detail,
                "v3_n2_stored_oos",
                challenger,
                n_bootstrap=n_bootstrap,
            )
            for challenger in [
                "spatial_p0080_l025_q50",
                "spatial_p0080_l025_calibrated",
            ]
        ],
        ignore_index=True,
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
            "train_samples": int(len(train)),
            "test_samples": int(len(test_idx)),
        })

    meta = {
        "purpose": "空间 GT 模型因果端到端上线门槛评估",
        "development_period": [
            DEV_START.strftime("%Y-%m-%d"),
            DEV_END.strftime("%Y-%m-%d"),
        ],
        "final_period": [
            FINAL_START.strftime("%Y-%m-%d"),
            final_end.strftime("%Y-%m-%d"),
        ],
        "target_development_acceptance_rate": target_rate,
        "temporal_rank_threshold": temporal_threshold,
        "temporal_development_acceptance_rate": temporal_dev_rate,
        "spatial_rank_threshold": spatial_threshold,
        "spatial_development_acceptance_rate": spatial_dev_rate,
        "execution_rule": "信号日收盘后决策，下一交易日开盘成交",
        "fee_rate": FEE_RATE,
        "spatial_pct": FINAL_PCT,
        "spatial_price_lambda": FINAL_LAMBDA,
        "bootstrap_samples": int(n_bootstrap),
        "folds": fold_meta,
        "notes": [
            "阈值仅按开发段放行率校准，测试段不使用未来 Top-K。",
            "stored OOS 为线上同谱系历史基线，不等于冻结生产二进制回放。",
            "项目引擎 Sharpe 对 DCA 现金流处理不是机构级口径，仅作仓库内诊断。",
            "cashflow_xirr 使用实际买入现金流与期末清算价值。",
        ],
    }

    OUTPUT_DIR.mkdir(exist_ok=True)
    summary_path = OUTPUT_DIR / "spatial_gt_e2e_summary.csv"
    trades_path = OUTPUT_DIR / "spatial_gt_e2e_trades.csv"
    bootstrap_path = OUTPUT_DIR / "spatial_gt_e2e_bootstrap.csv"
    meta_path = OUTPUT_DIR / "spatial_gt_e2e_meta.json"
    summary.to_csv(summary_path, index=False)
    trades.to_csv(trades_path, index=False)
    bootstrap.to_csv(bootstrap_path, index=False)
    with open(meta_path, "w", encoding="utf-8") as file:
        json.dump(meta, file, ensure_ascii=False, indent=2)

    display_columns = [
        "variant",
        "selected_count",
        "precision",
        "end_to_end_event_recall",
        "execution_overpay_median",
        "execution_overpay_mean",
        "execution_within_0_8pct_rate",
        "net_return_20d_mean",
        "cashflow_xirr",
    ]
    print(summary[display_columns].to_string(index=False))
    print("\n[Bootstrap]")
    print(bootstrap.to_string(index=False))
    print(f"\n[Output] {summary_path}")
    print(f"[Output] {trades_path}")
    print(f"[Output] {bootstrap_path}")
    print(f"[Output] {meta_path}")
    return {
        "summary": summary,
        "trades": trades,
        "bootstrap": bootstrap,
        "meta": meta,
    }


def main():
    run()


if __name__ == "__main__":
    main()
