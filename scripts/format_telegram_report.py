"""
把每日预测 JSON 渲染为 Telegram 友好的完整解释版报告。

只负责格式化，不抓数、不推理、不发送消息。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "output" / "daily_prediction.json"


FEATURE_NAMES = {
    "rsi_14": "RSI(14)",
    "rsi_min_3d": "近3日 RSI 低点",
    "ema20_dist": "收盘价相对 EMA20 距离",
    "consecutive_below_ema": "连续低于 EMA20 天数",
    "drawdown_from_high": "相对近60日高点回撤",
    "breadth": "站上20日均线的成分股比例",
    "breadth_c2": "连续弱势修正后的市场广度 C2",
    "breadth_min_3d": "近3日市场广度低点",
    "breadth_spread": "广度曲线分化",
    "breadth_delta_3d": "广度3日变化",
    "vix_regime": "VIX 波动区间",
    "vix_above_200ma": "VIX 是否高于200日均线",
    "sig_breadth": "市场广度恐慌信号",
    "sig_breadth_consec": "连续弱势广度信号",
    "sig_breadth_div": "广度背离信号",
    "sig_vix": "VIX 恐慌信号",
    "rsi_minus_ma": "RSI 相对短期均线",
    "sig_rsi_recent_3d": "近3日 RSI 信号",
    "sig_breadth_recent_3d": "近3日广度信号",
    "sig_breadth_div_recent_5d": "近5日广度背离信号",
    "confluence_5d": "近5日多信号共振",
}


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _num(x: object, digits: int = 2) -> str:
    if isinstance(x, (int, float)):
        return f"{x:.{digits}f}"
    return "N/A"


def _feature_label(name: str) -> str:
    return FEATURE_NAMES.get(name, name)


def _decision(r: dict, threshold: float) -> tuple[str, str]:
    is_signal = bool(r.get("is_signal_day"))
    probability = float(r.get("probability", 0.0))
    if not is_signal:
        return (
            "未进入买入观察场景",
            "今天没有满足 NDay5 条件。当前模型是在 NDay5 信号日样本上训练的，所以非信号日的概率只能作为市场温度参考，不能作为触发观察的依据。",
        )
    if probability >= threshold:
        return (
            "进入高优先级买入观察场景",
            f"今天满足 NDay5 条件，并且底部区域概率达到 {_pct(probability)}，高于 {_pct(threshold)} 的观察阈值。",
        )
    return (
        "进入观察场景，但概率不足",
        f"今天满足 NDay5 条件，但底部区域概率为 {_pct(probability)}，低于 {_pct(threshold)} 的观察阈值，说明模型证据还不够强。",
    )


def _market_state_paragraph(r: dict) -> str:
    fv = r.get("feature_values", {}) or {}
    consec = r.get("consecutive_below_ema")
    days = r.get("days_to_signal")
    parts = [
        f"价格层面，SPY 收盘为 {_num(r.get('spy_close'))}。"
    ]
    if consec is not None:
        parts.append(f"当前连续低于 EMA20 为 {consec} 天，距离 NDay5 触发还差 {days} 天。")
    if "ema20_dist" in fv:
        parts.append(f"收盘价相对 EMA20 的距离为 {_num(fv.get('ema20_dist'))}%，代表价格只是略低于20日趋势线。")
    if "rsi_14" in fv:
        parts.append(f"RSI(14) 为 {_num(fv.get('rsi_14'))}，不是典型的深度超卖读数。")
    if "breadth" in fv:
        parts.append(f"市场广度为 {_num(fv.get('breadth'))}%，说明仍有超过一半成分股站在20日均线上，市场内部没有出现广泛恐慌。")
    if "vix_regime" in fv:
        parts.append(f"VIX regime 为 {_num(fv.get('vix_regime'), 0)}，当前波动环境没有进入极端恐慌档。")
    return "".join(parts)


def _feature_sentence(name: str, value: float, current: object, direction: str) -> str:
    label = _feature_label(name)
    cur = _num(current, 3)
    abs_value = abs(value)

    explanations = {
        "drawdown_from_high": "它衡量价格从近60日高点回撤了多少。回撤越明显，模型越容易把市场识别为接近底部区域。",
        "consecutive_below_ema": "它描述价格在 EMA20 下方持续了多久。持续弱势是 NDay5 场景的核心背景。",
        "breadth_spread": "它描述不同广度曲线之间的分化。分化扩大时，模型会认为市场内部结构存在一定压力。",
        "ema20_dist": "它衡量价格距离20日趋势线的偏离程度。价格低于 EMA20 时，会提供一定弱势背景。",
        "rsi_minus_ma": "它衡量 RSI 相对自身短期均线的变化，反映动量是否正在恶化或修复。",
        "rsi_min_3d": "它看最近3天 RSI 的最低水平。当前 RSI 不够低时，模型会认为超卖证据不足。",
        "breadth_c2": "它衡量连续弱势调整后的市场广度。读数不够低时，说明市场还没有形成足够广泛的下跌压力。",
        "breadth_min_3d": "它看最近3天市场广度的低点。低点不够极端时，模型会降低底部判断强度。",
        "rsi_14": "它是常用超买超卖指标。当前数值越接近中性，越不支持极端底部判断。",
        "sig_rsi_recent_3d": "它表示近期是否出现 RSI 买入信号。没有出现时，会削弱底部判断。",
        "confluence_5d": "它衡量近期多类信号是否共振。共振越多，模型越倾向于提高观察优先级。",
    }
    reason = explanations.get(name, "它是模型训练中保留下来的特征之一，用来描述当前市场状态。")
    verb = "推高" if direction == "up" else "压低"
    return f"{label} 当前值为 {cur}，SHAP 贡献为 {value:+.3f}，这是一个{verb}底部概率的因素。{reason}"


def _top_shap(r: dict, limit: int = 4) -> tuple[list[tuple[str, float]], list[tuple[str, float]]]:
    shap = r.get("shap_contribs", {}) or {}
    positives = sorted(
        [(k, float(v)) for k, v in shap.items() if float(v) > 0],
        key=lambda kv: kv[1],
        reverse=True,
    )[:limit]
    negatives = sorted(
        [(k, float(v)) for k, v in shap.items() if float(v) < 0],
        key=lambda kv: kv[1],
    )[:limit]
    return positives, negatives


def _name_value_pairs(items: list[tuple[str, float]], fv: dict) -> str:
    parts = []
    for name, value in items:
        label = _feature_label(name)
        current = _num(fv.get(name), 3)
        parts.append(f"{label}（当前 {current}，贡献 {value:+.3f}）")
    return "、".join(parts)


def _shap_synthesis_paragraph(r: dict) -> str:
    fv = r.get("feature_values", {}) or {}
    positives, negatives = _top_shap(r)
    pos_text = _name_value_pairs(positives, fv) if positives else "没有特别强的正向因子"
    neg_text = _name_value_pairs(negatives, fv) if negatives else "没有特别强的负向因子"

    is_signal = bool(r.get("is_signal_day"))
    probability = float(r.get("probability", 0.0))
    if is_signal:
        opening = (
            f"整体来看，今天已经进入 NDay5 场景，模型给出的底部区域概率为 {_pct(probability)}。"
        )
    else:
        opening = (
            f"整体来看，今天没有进入 NDay5 场景，模型给出的 {_pct(probability)} 更适合理解为市场温度，而不是行动信号。"
        )

    return (
        f"{opening}"
        f"模型确实看到了一些会推高底部概率的迹象，主要来自 {pos_text}。"
        "这些因素共同说明市场并非完全强势，价格或内部结构已经出现一定压力。"
        f"但更关键的是，压低概率的证据也很明显，主要来自 {neg_text}。"
        "这组证据说明当前压力还没有发展成模型偏好的深度超卖、广泛恐慌或持续弱势状态。"
        "因此，正负因素合在一起并不矛盾：它们表达的是同一个结论，即市场有轻度压力或局部弱化，但证据还不足以确认进入高质量底部观察区。"
    )


def build_report(r: dict, threshold: float = 0.5) -> str:
    title = f"SPY 每日模型报告 - {r.get('as_of_date', 'N/A')}"
    decision, decision_reason = _decision(r, threshold)
    fresh = r.get("data_freshness", {}) or {}
    probability = float(r.get("probability", 0.0))
    ho = r.get("holdout_metrics", {}) or {}

    lines = [
        title,
        "",
        f"结论：{decision}",
        f"底部区域概率：{_pct(probability)}",
        f"观察阈值：{_pct(threshold)}",
        f"NDay5：{'是' if r.get('is_signal_day') else '否'}",
        f"SPY 收盘：{_num(r.get('spy_close'))}",
        "",
        "一、结论解释",
        decision_reason,
        "",
        "二、数据新鲜度",
        f"SPY: {fresh.get('SPY', 'N/A')}",
        f"VIX: {fresh.get('VIX', 'N/A')}",
        f"Breadth: {fresh.get('breadth', 'N/A')}",
        "",
        "三、当前市场状态",
        _market_state_paragraph(r),
        "",
        "四、为什么模型会给出这个概率",
        _shap_synthesis_paragraph(r),
    ]

    lines.extend([
        "",
        "五、操作含义",
    ])
    if not r.get("is_signal_day"):
        lines.append("今天不进入模型定义的买入观察场景。当前更适合继续观察，而不是把模型概率当作行动信号。")
    elif probability >= threshold:
        lines.append("今天进入高优先级买入观察场景。更合理的做法是结合仓位规则、风险预算和人工复核，再决定是否执行。")
    else:
        lines.append("今天满足 NDay5 场景，但概率没有超过阈值。可以记录为观察日，但不应视为强信号。")

    lines.extend([
        "",
        "六、模型可靠性",
    ])
    if ho.get("auc_roc"):
        lines.append(
            f"样本外 AUC-ROC 为 {ho['auc_roc']:.3f}，说明模型有一定区分能力，但仍属于弱信号。"
        )
    else:
        lines.append("本次 JSON 中没有找到样本外 AUC 指标。")
    lines.append("本报告仅供研究观察，不构成投资建议。")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 Telegram 友好的每日解释报告")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--threshold", type=float, default=0.5)
    args = parser.parse_args()

    with args.input.open(encoding="utf-8") as f:
        result = json.load(f)
    print(build_report(result, threshold=args.threshold))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
