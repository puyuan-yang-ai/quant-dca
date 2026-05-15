#!/usr/bin/env bash
# 交互式策略图表查看 — 自动使用 venv 环境
# 用法：./show_chart.sh [--env bear|bull|bear-bull|bull-bear]
cd "$(dirname "$0")"
exec .venv/bin/python -u scripts/show_chart.py "$@"
