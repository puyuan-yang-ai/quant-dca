import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.font_manager as fm
import numpy as np
from datetime import datetime, timedelta
import os

font_path = os.path.expanduser("~/.fonts/NotoSansSC-Regular.ttf")
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    prop = fm.FontProperties(fname=font_path)
    plt.rcParams["font.family"] = prop.get_name()
else:
    plt.rcParams["font.family"] = "DejaVu Sans"
plt.rcParams["axes.unicode_minus"] = False

fig, ax = plt.subplots(figsize=(16, 8))
fig.patch.set_facecolor("#FAFAFA")
ax.set_facecolor("#FAFAFA")

# --- Actual data (6/5 - 6/9 close) ---
actual_dates = [datetime(2026, 6, 5), datetime(2026, 6, 8), datetime(2026, 6, 9)]
actual_close = [7400.5, 7416.0, 7392.8]

ax.plot(actual_dates, actual_close, "o-", color="#1a1a1a", linewidth=2.5, markersize=7, zorder=10, label="实际收盘")

# 6/5 intraday low
ax.plot(datetime(2026, 6, 5), 7359, "v", color="#D32F2F", markersize=10, zorder=11)
ax.annotate("6/5 Low\n7359", xy=(datetime(2026, 6, 5), 7359),
            xytext=(-50, -35), textcoords="offset points",
            fontsize=9, fontweight="bold", color="#D32F2F",
            arrowprops=dict(arrowstyle="->", color="#D32F2F", lw=1.2))

# 6/9 intraday range (the "needle")
d69 = datetime(2026, 6, 9)
ax.plot([d69, d69], [7247, 7491], color="#D32F2F", linewidth=2, zorder=9)
ax.plot(d69, 7491, "^", color="#2E7D32", markersize=10, zorder=11)
ax.plot(d69, 7247, "v", color="#D32F2F", markersize=10, zorder=11)
ax.annotate("V/J 冲高\n7491", xy=(d69, 7491),
            xytext=(15, 15), textcoords="offset points",
            fontsize=9, fontweight="bold", color="#2E7D32",
            arrowprops=dict(arrowstyle="->", color="#2E7D32", lw=1.2))
ax.annotate("暴跌低点\n7247", xy=(d69, 7247),
            xytext=(15, -30), textcoords="offset points",
            fontsize=9, fontweight="bold", color="#D32F2F",
            arrowprops=dict(arrowstyle="->", color="#D32F2F", lw=1.2))

# --- Scenario B (main, 50%) ---
b_dates = [datetime(2026, 6, 9), datetime(2026, 6, 10), datetime(2026, 6, 12),
           datetime(2026, 6, 14), datetime(2026, 6, 17),
           datetime(2026, 6, 20), datetime(2026, 6, 25),
           datetime(2026, 6, 29), datetime(2026, 7, 3)]
b_prices = [7392.8, 7360, 7340, 7300, 7420, 7380, 7310, 7330, 7460]

ax.plot(b_dates, b_prices, "o-", color="#1565C0", linewidth=2.5, markersize=6, zorder=8, label="B 主剧本 (50%) 延长磨底")

b_upper = [p + 50 for p in b_prices]
b_lower = [p - 50 for p in b_prices]
b_dates_np = mdates.date2num(b_dates)
ax.fill_between(b_dates, b_lower, b_upper, alpha=0.12, color="#1565C0", zorder=2)

ax.annotate("6/13-14\nSolar-Lunar Low\n二次探底", xy=(datetime(2026, 6, 14), 7300),
            xytext=(-80, -40), textcoords="offset points",
            fontsize=8.5, fontweight="bold", color="#1565C0",
            arrowprops=dict(arrowstyle="->", color="#1565C0", lw=1.2))
ax.annotate("6/17-18\n弱反弹高点", xy=(datetime(2026, 6, 17), 7420),
            xytext=(10, 20), textcoords="offset points",
            fontsize=8.5, color="#1565C0",
            arrowprops=dict(arrowstyle="->", color="#1565C0", lw=1))
ax.annotate("6/26-29 CRD\n磨底确认", xy=(datetime(2026, 6, 29), 7330),
            xytext=(-15, -40), textcoords="offset points",
            fontsize=8.5, fontweight="bold", color="#1565C0",
            arrowprops=dict(arrowstyle="->", color="#1565C0", lw=1.2))
ax.annotate("7月初\n恢复上行", xy=(datetime(2026, 7, 3), 7460),
            xytext=(10, 15), textcoords="offset points",
            fontsize=8.5, fontweight="bold", color="#1565C0",
            arrowprops=dict(arrowstyle="->", color="#1565C0", lw=1))

# --- Scenario A (optimistic, 25%) ---
a_dates = [datetime(2026, 6, 9), datetime(2026, 6, 10), datetime(2026, 6, 12),
           datetime(2026, 6, 14), datetime(2026, 6, 17),
           datetime(2026, 6, 20), datetime(2026, 6, 25),
           datetime(2026, 6, 29), datetime(2026, 7, 3)]
a_prices = [7392.8, 7380, 7370, 7380, 7480, 7520, 7580, 7640, 7700]

ax.plot(a_dates, a_prices, "o--", color="#2E7D32", linewidth=1.8, markersize=5, alpha=0.7, zorder=6, label="A 乐观 (25%) 快速见底")
ax.annotate("6/13-14\nhigher-low 筑底", xy=(datetime(2026, 6, 14), 7380),
            xytext=(15, -25), textcoords="offset points",
            fontsize=8, color="#2E7D32", alpha=0.8,
            arrowprops=dict(arrowstyle="->", color="#2E7D32", lw=1, alpha=0.7))
ax.annotate("Primary Crest\n7700", xy=(datetime(2026, 7, 3), 7700),
            xytext=(5, 15), textcoords="offset points",
            fontsize=8, fontweight="bold", color="#2E7D32", alpha=0.8)

# --- Scenario C (bearish, 25%) ---
c_dates = [datetime(2026, 6, 9), datetime(2026, 6, 10), datetime(2026, 6, 12),
           datetime(2026, 6, 14), datetime(2026, 6, 17),
           datetime(2026, 6, 20), datetime(2026, 6, 25),
           datetime(2026, 6, 29), datetime(2026, 7, 3)]
c_prices = [7392.8, 7340, 7300, 7240, 7280, 7220, 7200, 7180, 7250]

ax.plot(c_dates, c_prices, "o--", color="#D32F2F", linewidth=1.8, markersize=5, alpha=0.7, zorder=6, label="C 悲观 (25%) 破 MCL 深跌")
ax.annotate("破 MCL\n加速下行", xy=(datetime(2026, 6, 14), 7240),
            xytext=(-75, -25), textcoords="offset points",
            fontsize=8, color="#D32F2F", alpha=0.8,
            arrowprops=dict(arrowstyle="->", color="#D32F2F", lw=1, alpha=0.7))
ax.annotate("7230 止损", xy=(datetime(2026, 6, 20), 7220),
            xytext=(-60, -20), textcoords="offset points",
            fontsize=8, color="#D32F2F", alpha=0.8,
            arrowprops=dict(arrowstyle="->", color="#D32F2F", lw=1, alpha=0.7))

# --- Reference lines ---
ax.axhline(y=7497, color="#FF9800", linewidth=1.2, linestyle="--", alpha=0.7, zorder=3)
ax.text(datetime(2026, 7, 4), 7497, " TIP 7497", fontsize=8, color="#FF9800", va="bottom", fontweight="bold")

ax.axhline(y=7354, color="#D32F2F", linewidth=1.5, linestyle="--", alpha=0.7, zorder=3)
ax.text(datetime(2026, 7, 4), 7354, " MCL 7354", fontsize=8, color="#D32F2F", va="bottom", fontweight="bold")

ax.axhline(y=7230, color="#B71C1C", linewidth=1.5, linestyle="-.", alpha=0.6, zorder=3)
ax.text(datetime(2026, 7, 4), 7230, " 止损 7230", fontsize=8, color="#B71C1C", va="bottom", fontweight="bold")

# --- Vertical event markers ---
for d, lbl, c in [
    (datetime(2026, 6, 9), "V/J 合相", "#FF9800"),
    (datetime(2026, 6, 14), "Solar-Lunar\nLow 140.8★", "#7B1FA2"),
    (datetime(2026, 6, 29), "CRD ★", "#1565C0"),
]:
    ax.axvline(x=d, color=c, linewidth=0.8, linestyle=":", alpha=0.5, zorder=1)
    ax.text(d, 7130, lbl, fontsize=7.5, color=c, ha="center", va="bottom", fontstyle="italic")

# --- Formatting ---
ax.set_xlim(datetime(2026, 6, 4), datetime(2026, 7, 5))
ax.set_ylim(7100, 7750)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%-m/%-d"))
ax.xaxis.set_major_locator(mdates.DayLocator(interval=2))
ax.set_xlabel("日期", fontsize=11)
ax.set_ylabel("ES 点位", fontsize=11)
ax.set_title("ES 走势剧本推演（2026-06-10 更新）\n主剧本 B: 延长修正磨底 → 6/26-29 CRD 确认底部 → 7月恢复", fontsize=13, fontweight="bold", pad=15)
ax.legend(loc="upper right", fontsize=9, framealpha=0.9)
ax.grid(True, alpha=0.3, linestyle="-")
ax.tick_params(axis="x", rotation=30)

plt.tight_layout()
output_path = "/home/puyuyang/Projects/quant-dca/docs/tasks/mma-report/mma_weekly_20260608/scenario_B_chart_20260610.png"
fig.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="#FAFAFA")
print(f"Chart saved to: {output_path}")
