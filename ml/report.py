"""
每日报告生成器 — 读推理 JSON，渲染人可读的 Markdown 报告

与 predict.py 解耦：predict.py 负责算（输出结构化 JSON），
report.py 负责把数字整理成给人看的报告。这样改报告格式不影响推理逻辑。

使用：
  python -m ml.report                                    # 读默认 JSON，写 reports/<日期>.md
  python -m ml.report --input output/daily_prediction.json
  python -m ml.report --stdout                           # 只打印到终端，不落盘

输出：
  reports/<as_of_date>.md
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
DEFAULT_INPUT = ROOT / "output" / "daily_prediction.json"
REPORTS_DIR = ROOT / "reports"


def _fmt_pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def build_markdown(r: dict) -> str:
    """把推理结果字典渲染成 Markdown 报告字符串"""
    is_signal = r.get("is_signal_day", False)
    proba = r.get("probability", 0.0)
    fv = r.get("feature_values", {})
    imp = r.get("feature_importance", {})
    fresh = r.get("data_freshness", {})
    ho = r.get("holdout_metrics", {}) or {}

    signal_line = (
        "✅ **是信号日**（满足 NDay5：连续 5 天收盘低于 EMA20）"
        if is_signal else
        "❌ **非信号日**"
    )

    lines = []
    lines.append(f"# SPY 底部信号每日报告 — {r.get('as_of_date', 'N/A')}")
    lines.append("")
    lines.append("> 仅供研究观察，非投资建议。模型为弱信号（样本外 AUC-ROC≈0.66），请勿据此直接交易。")
    lines.append("")

    # --- 核心结论 ---
    lines.append("## 核心结论")
    lines.append("")
    lines.append(f"- 数据截止：**{r.get('as_of_date', 'N/A')}**")
    lines.append(f"- SPY 收盘：**{r.get('spy_close', 0):.2f}**")
    lines.append(f"- NDay5 状态：{signal_line}")
    if not is_signal:
        consec = r.get("consecutive_below_ema")
        days = r.get("days_to_signal")
        if consec is not None:
            lines.append(f"  - 连续低于 EMA20：{consec} 天（还差 {days} 天触发信号）")
    lines.append(f"- **底部区域概率：{_fmt_pct(proba)}**")
    if not is_signal:
        lines.append("")
        lines.append("> ⚠️ 今日非信号日，模型未在此场景训练，上述概率仅供参考，不可作为依据。")
    lines.append("")

    # --- 模型可靠性 ---
    lines.append("## 模型可靠性")
    lines.append("")
    if ho.get("auc_roc"):
        lines.append(f"- 样本外 AUC-ROC：**{ho['auc_roc']:.3f}**（0.5=瞎猜，1.0=完美；当前为弱信号）")
        lines.append(f"- 样本外 AUC-PR：{ho.get('auc_pr', 0):.3f}")
        tp = ho.get("test_period")
        if tp:
            lines.append(f"- 评估区间：{tp[0]} ~ {tp[1]}（{ho.get('test_samples', 0)} 个信号样本）")
    else:
        lines.append("- 暂无样本外评估指标")
    tr = r.get("train_period")
    if tr:
        lines.append(f"- 训练区间：{tr[0]} ~ {tr[1]}，正标签比例 {_fmt_pct(r.get('train_pos_rate', 0))}")
    lines.append("")

    # --- 模型判断依据：feature importance + 当前取值 ---
    lines.append("## 模型判断依据（特征重要度 & 当前取值）")
    lines.append("")
    lines.append("| 特征 | 重要度 | 当前值 |")
    lines.append("| --- | ---: | ---: |")
    top = sorted(imp.items(), key=lambda kv: kv[1], reverse=True)
    for name, val in top:
        cur = fv.get(name)
        cur_str = f"{cur:.3f}" if isinstance(cur, (int, float)) else "—"
        lines.append(f"| {name} | {val:.4f} | {cur_str} |")
    lines.append("")

    # --- 数据新鲜度 ---
    lines.append("## 数据新鲜度")
    lines.append("")
    for k, v in fresh.items():
        flag = "" if v == r.get("as_of_date") else "  ⚠️ 落后于推理日期"
        lines.append(f"- {k}: {v}{flag}")
    lines.append("")

    # --- 元信息 ---
    lines.append("---")
    lines.append("")
    lines.append(f"- 模型版本：{r.get('version', 'N/A')}")
    lines.append(f"- 推理时间(UTC)：{r.get('predicted_at_utc', 'N/A')}")
    lines.append("")

    return "\n".join(lines)


def generate(input_path: Path = None, to_stdout: bool = False) -> Path | None:
    """读取 JSON，生成报告。返回报告文件路径（stdout 模式返回 None）"""
    input_path = input_path or DEFAULT_INPUT
    if not input_path.exists():
        raise FileNotFoundError(
            f"推理结果不存在: {input_path}\n请先运行 python -m ml.predict --json {input_path}"
        )
    with open(input_path, encoding="utf-8") as f:
        r = json.load(f)

    md = build_markdown(r)

    if to_stdout:
        print(md)
        return None

    REPORTS_DIR.mkdir(exist_ok=True)
    out_path = REPORTS_DIR / f"{r.get('as_of_date', 'unknown')}.md"
    out_path.write_text(md, encoding="utf-8")
    print(f"[Report] 报告已生成: {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="生成每日 Markdown 报告")
    parser.add_argument("--input", type=str, default=None, help="推理 JSON 路径")
    parser.add_argument("--stdout", action="store_true", help="只打印不落盘")
    args = parser.parse_args()

    input_path = Path(args.input) if args.input else None
    generate(input_path=input_path, to_stdout=args.stdout)


if __name__ == "__main__":
    main()
