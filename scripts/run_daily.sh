#!/bin/bash
#
# 每日推理总流程 — launchd 每天定时调用本脚本
#
# 流程: 激活环境 → 等网络就绪 → 增量更新数据 → 推理 → 出报告 → 推送
# 设计要点:
#   - launchd 启动时环境变量近乎为空, 因此全部用绝对路径、脚本内自定 PATH
#   - Mac 刚唤醒可能网络未就绪, 故先探测网络 + 重试
#   - 每一步失败都写日志并推送 Telegram 告警, 避免"默默跑挂"
#   - 日志按日期落到 logs/
#
# 手动运行: bash scripts/run_daily.sh
# 只生成本地结果、不发送成功报告: bash scripts/run_daily.sh --no-notify

set -uo pipefail

# ─────────────────────────────────────────────
# 配置区: 项目根目录 (改成你 Mac mini 上的实际路径)
# ─────────────────────────────────────────────
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"
LOG_DIR="${PROJECT_ROOT}/logs"
JSON_OUT="${PROJECT_ROOT}/output/daily_prediction.json"
SEND_SUCCESS_NOTIFY=1

for arg in "$@"; do
    case "${arg}" in
        --no-notify)
            SEND_SUCCESS_NOTIFY=0
            ;;
        *)
            echo "未知参数: ${arg}" >&2
            echo "用法: bash scripts/run_daily.sh [--no-notify]" >&2
            exit 2
            ;;
    esac
done

# launchd 环境干净, 显式补 PATH (含 Homebrew 路径, 供 curl 等)
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/daily_$(date +%Y%m%d).log"

# ─────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "${LOG_FILE}"
}

# 推送告警 (失败时调用; 用 notify.py 的 --text, 不依赖 JSON)
alert() {
    local msg="$1"
    log "ALERT: ${msg}"
    "${VENV_PYTHON}" -m ml.notify --text "[ALERT] 每日推理失败: ${msg}" >> "${LOG_FILE}" 2>&1 || \
        log "（告警推送本身也失败了, 仅记录日志）"
}

# 网络探测: 重试至多 N 次, 每次间隔递增
wait_for_network() {
    local max_tries=6
    local i=1
    while [ "${i}" -le "${max_tries}" ]; do
        if curl -s --max-time 10 -o /dev/null "https://query1.finance.yahoo.com" 2>/dev/null; then
            log "网络就绪 (第 ${i} 次探测)"
            return 0
        fi
        log "网络未就绪, 第 ${i}/${max_tries} 次, 等待 $((i * 10)) 秒..."
        sleep $((i * 10))
        i=$((i + 1))
    done
    return 1
}

run_with_retry() {
    local desc="$1"
    shift
    log "${desc}..."
    if "$@" >> "${LOG_FILE}" 2>&1; then
        return 0
    fi
    log "${desc}失败, 5 秒后重试一次..."
    sleep 5
    "$@" >> "${LOG_FILE}" 2>&1
}

# ─────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────
log "========== 每日推理开始 =========="
cd "${PROJECT_ROOT}" || { log "无法进入项目目录"; exit 1; }

# 0) 检查 venv
if [ ! -x "${VENV_PYTHON}" ]; then
    log "错误: 找不到 venv Python (${VENV_PYTHON}), 请先 python3 -m venv .venv && pip install -r requirements.txt"
    exit 1
fi

# 1) 等网络
if ! wait_for_network; then
    alert "网络始终不可用, 已放弃 (在最后一次唤醒/调度点重试无效)"
    log "========== 异常结束 (网络) =========="
    exit 1
fi

# 2) 统一增量更新模型所需数据：SPY / VIX / S&P 500 Breadth
# 数据必须完整更新；失败则停止当天报告并推送告警。
if ! run_with_retry "步骤 1/4: 增量更新市场数据" "${VENV_PYTHON}" scripts/update_market_data.py; then
    alert "市场数据更新失败 (重试后仍失败)，已停止当天报告"
    log "========== 异常结束 (update_market_data) =========="
    exit 1
fi

# 3) 推理
log "步骤 2/4: 模型推理..."
if ! "${VENV_PYTHON}" -m ml.predict --json "${JSON_OUT}" >> "${LOG_FILE}" 2>&1; then
    alert "模型推理失败"
    log "========== 异常结束 (predict) =========="
    exit 1
fi

# 4) 出报告
log "步骤 3/4: 生成报告..."
if ! "${VENV_PYTHON}" -m ml.report --input "${JSON_OUT}" >> "${LOG_FILE}" 2>&1; then
    alert "报告生成失败"
    log "========== 异常结束 (report) =========="
    exit 1
fi

# 5) 推送 (推送失败不算致命, 但要记录)
if [ "${SEND_SUCCESS_NOTIFY}" -eq 1 ]; then
    log "步骤 4/4: Telegram 推送..."
    if ! "${VENV_PYTHON}" -m ml.notify --json "${JSON_OUT}" >> "${LOG_FILE}" 2>&1; then
        log "警告: 推送失败 (报告已生成, 可手动查看 reports/)"
    fi
else
    log "步骤 4/4: 跳过 Telegram 成功推送 (--no-notify)"
fi

log "========== 每日推理完成 =========="
exit 0
