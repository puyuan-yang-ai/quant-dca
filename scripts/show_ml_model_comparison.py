"""
ML 双模型交互式对比图。

生成 v3 原版模型与 v3_n2 当前生产模型的回放结果，并用项目原生
Lightweight Charts 图表展示：主图 K 线/EMA/买点，副图概率曲线/阈值线。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ml.labeling import load_spy  # noqa: E402
from src.indicators import calc_ema  # noqa: E402
from src.interactive_chart import show_ml_model_comparison_chart  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_V3_ROOT = Path("/home/puyuyang/Projects/quant-dca-v3-original")
DEFAULT_SHAP_DATES = [
    "2026-06-09",
    "2026-06-10",
    "2026-06-11",
    "2026-06-25",
    "2026-06-26",
]


def _run_export(version: str, repo_root: Path, data_root: Path, start: str,
                end: str | None, output: Path, shap_dates: list[str]) -> None:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "export_ml_model_replay.py"),
        "--repo-root", str(repo_root),
        "--data-root", str(data_root),
        "--version", version,
        "--start", start,
        "--output", str(output),
        "--shap-dates", *shap_dates,
    ]
    if end:
        cmd.extend(["--end", end])
    subprocess.run(cmd, cwd=str(ROOT), check=True)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _row_by_date(payload: dict) -> dict[str, dict]:
    return {row["date"]: row for row in payload["rows"]}


def _build_candles_and_ema(start: str, end: str) -> tuple[list[dict], list[dict]]:
    spy = load_spy()
    mask = (spy["date"] >= start) & (spy["date"] <= end)
    data = spy[mask].copy().reset_index(drop=True)

    candles = [
        {
            "time": row["date"].strftime("%Y-%m-%d"),
            "open": round(float(row["open"]), 2),
            "high": round(float(row["high"]), 2),
            "low": round(float(row["low"]), 2),
            "close": round(float(row["close"]), 2),
        }
        for _, row in data.iterrows()
    ]

    ema_values = calc_ema(data["close"].astype(float).tolist(), 20)
    ema_data = [
        {
            "time": data.iloc[i]["date"].strftime("%Y-%m-%d"),
            "value": round(float(value), 2),
        }
        for i, value in enumerate(ema_values)
        if value is not None
    ]
    return candles, ema_data


def _prob_series(payload: dict, name: str, color: str) -> dict:
    return {
        "name": name,
        "color": color,
        "lineWidth": 2,
        "data": [
            {"time": row["date"], "value": round(float(row["probability"]), 4)}
            for row in payload["rows"]
        ],
    }


def _build_markers_for_view(v3_rows: dict[str, dict], n2_rows: dict[str, dict],
                            focus_dates: set[str], buy_key: str,
                            view_label: str) -> tuple[list[dict], dict]:
    markers: list[dict] = []
    dates = sorted(set(v3_rows) | set(n2_rows))
    v3_buy_count = n2_buy_count = both_buy_count = 0

    for date in dates:
        v3 = v3_rows.get(date)
        n2 = n2_rows.get(date)
        v3_buy = bool(v3 and v3.get(buy_key))
        n2_buy = bool(n2 and n2.get(buy_key))

        if v3_buy:
            v3_buy_count += 1
        if n2_buy:
            n2_buy_count += 1
        if v3_buy and n2_buy:
            both_buy_count += 1
            markers.append({
                "time": date,
                "position": "belowBar",
                "shape": "arrowUp",
                "color": "#FFD54F",
                "text": f"BOTH {view_label} v3={v3['probability']:.2f} n2={n2['probability']:.2f}",
            })
        elif v3_buy:
            markers.append({
                "time": date,
                "position": "belowBar",
                "shape": "arrowUp",
                "color": "#AB47BC",
                "text": f"v3 BUY {view_label} p={v3['probability']:.2f}",
            })
        elif n2_buy:
            markers.append({
                "time": date,
                "position": "belowBar",
                "shape": "arrowUp",
                "color": "#26A69A",
                "text": f"v3_n2 BUY {view_label} p={n2['probability']:.2f}",
            })

    for date in sorted(focus_dates):
        markers.append({
            "time": date,
            "position": "aboveBar",
            "shape": "circle",
            "color": "#FF9800",
            "text": "低点簇",
        })

    summary = {
        "v3_buy_count": v3_buy_count,
        "v3_n2_buy_count": n2_buy_count,
        "both_buy_count": both_buy_count,
    }
    return markers, summary


def _build_marker_sets(v3_rows: dict[str, dict], n2_rows: dict[str, dict],
                       focus_dates: set[str]) -> tuple[dict[str, list[dict]], dict]:
    default_markers, default_summary = _build_markers_for_view(
        v3_rows, n2_rows, focus_dates, "buy_default", "default",
    )
    unified_markers, unified_summary = _build_markers_for_view(
        v3_rows, n2_rows, focus_dates, "buy_at_035", "0.35",
    )
    return (
        {"default": default_markers, "unified035": unified_markers},
        {"default": default_summary, "unified035": unified_summary},
    )


def _compact_detail(row: dict | None) -> dict | None:
    if not row:
        return None
    return {
        "probability": row.get("probability"),
        "n_days": row.get("n_days"),
        "is_signal_day": row.get("is_signal_day"),
        "consecutive_below_ema": row.get("consecutive_below_ema"),
        "threshold_default": row.get("threshold_default"),
        "buy_default": row.get("buy_default"),
        "buy_at_035": row.get("buy_at_035"),
        "shap": row.get("shap"),
    }


def _build_detail_map(v3_rows: dict[str, dict], n2_rows: dict[str, dict]) -> dict[str, dict]:
    detail = {}
    for date in sorted(set(v3_rows) | set(n2_rows)):
        detail[date] = {
            "v3": _compact_detail(v3_rows.get(date)),
            "v3_n2": _compact_detail(n2_rows.get(date)),
        }
    return detail


def main():
    parser = argparse.ArgumentParser(description="生成 ML 双模型交互式对比图")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--port", type=int, default=9871)
    parser.add_argument("--v3-root", type=Path, default=DEFAULT_V3_ROOT)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output")
    parser.add_argument("--shap-dates", nargs="*", default=DEFAULT_SHAP_DATES)
    parser.add_argument("--reuse", action="store_true",
                        help="复用已有 output/ml_replay_*.json，不重新导出")
    args = parser.parse_args()

    if not args.v3_root.exists():
        raise FileNotFoundError(f"未找到 v3 历史 worktree: {args.v3_root}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    data_root = ROOT / "data"
    v3_json = args.output_dir / "ml_replay_v3.json"
    n2_json = args.output_dir / "ml_replay_v3_n2.json"

    if not args.reuse:
        _run_export("v3", args.v3_root, data_root, args.start, args.end, v3_json, args.shap_dates)
        _run_export("v3_n2", ROOT, data_root, args.start, args.end, n2_json, args.shap_dates)

    v3_payload = _load_json(v3_json)
    n2_payload = _load_json(n2_json)
    chart_start = max(v3_payload["start"], n2_payload["start"])
    chart_end = min(v3_payload["end"], n2_payload["end"])

    candles, ema_data = _build_candles_and_ema(chart_start, chart_end)
    v3_rows = _row_by_date(v3_payload)
    n2_rows = _row_by_date(n2_payload)
    focus_dates = set(args.shap_dates)
    marker_sets, marker_summary_by_view = _build_marker_sets(v3_rows, n2_rows, focus_dates)

    probability_series = [
        _prob_series(v3_payload, "v3 / NDay5", "#AB47BC"),
        _prob_series(n2_payload, "v3_n2 / NDay2", "#26A69A"),
    ]
    threshold_lines = [
        {"value": 0.50, "color": "#AB47BC", "label": "v3 0.50"},
        {"value": 0.35, "color": "#26A69A", "label": "v3_n2 0.35"},
    ]
    detail_map = _build_detail_map(v3_rows, n2_rows)
    summary = {
        "range": f"{chart_start} ~ {chart_end}",
        "views": marker_summary_by_view,
    }

    title = f"SPY ML 模型对比：v3 vs v3_n2（{chart_start} ~ {chart_end}）"
    show_ml_model_comparison_chart(
        candles=candles,
        ema_data=ema_data,
        markers=marker_sets,
        probability_series=probability_series,
        threshold_lines=threshold_lines,
        detail_map=detail_map,
        summary=summary,
        title=title,
        output_dir=str(args.output_dir),
        port=args.port,
    )


if __name__ == "__main__":
    main()
