"""
Telegram 推送 — 把每日预测摘要发到手机

推送逻辑独立成模块：将来想换渠道（邮件/Bark）只改这里。

配置（放 .env，不进 git）：
  TELEGRAM_BOT_TOKEN=...
  TELEGRAM_CHAT_ID=...
  TELEGRAM_PROXY=...   # 可选，网络受限时走代理（如 http://127.0.0.1:7890）

使用：
  python -m ml.notify --json output/daily_prediction.json           # 真实推送
  python -m ml.notify --json output/daily_prediction.json --dry-run # 只打印消息，不发送
  python -m ml.notify --text "自定义消息"                            # 直接发一段文字
  python -m ml.notify --text "测试" --dry-run                        # 验证渠道配置/格式

退出码：0 成功；非 0 失败（供 run_daily.sh 判断是否告警）。
"""
import argparse
import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent
DEFAULT_INPUT = ROOT / "output" / "daily_prediction.json"
ENV_FILE = ROOT / ".env"

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _load_env() -> dict:
    """从环境变量 + .env 文件读取配置（环境变量优先）"""
    cfg = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            cfg[key.strip()] = val.strip()
    # 环境变量覆盖 .env
    for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "TELEGRAM_PROXY"):
        if os.environ.get(key):
            cfg[key] = os.environ[key]
    return cfg


def _fmt_pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def build_summary(r: dict) -> str:
    """从推理结果构造一条精简的推送消息（纯文本，避免 Markdown 转义麻烦）"""
    is_signal = r.get("is_signal_day", False)
    signal_str = "✅ 信号日(NDay5触发)" if is_signal else "❌ 非信号日"
    lines = [
        f"📊 SPY 底部信号 {r.get('as_of_date', 'N/A')}",
        f"收盘: {r.get('spy_close', 0):.2f}",
        f"状态: {signal_str}",
        f"底部概率: {_fmt_pct(r.get('probability', 0))}",
    ]
    if not is_signal:
        consec = r.get("consecutive_below_ema")
        if consec is not None:
            lines.append(f"(连续低于EMA20 {consec}天, 还差{r.get('days_to_signal')}天)")
        lines.append("⚠️ 非信号日概率仅供参考")
    ho = r.get("holdout_metrics", {}) or {}
    if ho.get("auc_roc"):
        lines.append(f"模型AUC: {ho['auc_roc']:.3f} (弱信号)")
    lines.append("—— 仅供研究, 非投资建议")
    return "\n".join(lines)


def send_telegram(text: str, cfg: dict, dry_run: bool = False) -> bool:
    """发送 Telegram 消息。dry_run=True 时只打印不发送。返回是否成功。"""
    if dry_run:
        print("=" * 50)
        print("  [DRY-RUN] 将要发送的消息内容：")
        print("=" * 50)
        print(text)
        print("=" * 50)
        print("  [DRY-RUN] 未实际发送（--dry-run 模式）")
        return True

    token = cfg.get("TELEGRAM_BOT_TOKEN")
    chat_id = cfg.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[Notify] 错误：缺少 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID（检查 .env）", file=sys.stderr)
        return False

    proxy = cfg.get("TELEGRAM_PROXY")
    proxies = {"http": proxy, "https": proxy} if proxy else None

    try:
        resp = requests.post(
            TELEGRAM_API.format(token=token),
            data={"chat_id": chat_id, "text": text},
            proxies=proxies,
            timeout=20,
        )
        if resp.status_code == 200 and resp.json().get("ok"):
            print("[Notify] Telegram 推送成功")
            return True
        print(f"[Notify] Telegram 推送失败: {resp.status_code} {resp.text}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[Notify] Telegram 推送异常: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Telegram 推送每日摘要")
    parser.add_argument("--json", type=str, default=None, help="推理 JSON 路径（构造摘要）")
    parser.add_argument("--text", type=str, default=None, help="直接发送的自定义文本")
    parser.add_argument("--dry-run", action="store_true", help="只打印消息不发送")
    args = parser.parse_args()

    cfg = _load_env()

    if args.text:
        text = args.text
    else:
        input_path = Path(args.json) if args.json else DEFAULT_INPUT
        if not input_path.exists():
            print(f"[Notify] 错误：推理结果不存在 {input_path}", file=sys.stderr)
            sys.exit(1)
        with open(input_path, encoding="utf-8") as f:
            text = build_summary(json.load(f))

    ok = send_telegram(text, cfg, dry_run=args.dry_run)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
