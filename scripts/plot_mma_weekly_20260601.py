#!/usr/bin/env python3
"""Generate MMA weekly scenario projection chart for 20260601 report (offline, no CSV needed)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "docs" / "tasks" / "mma-report" / "mma_weekly_20260601"

# ── From scenario_evolution.md (20260601 weekly, final state 2026-06-06) ──
# Latest known close: 6/5 final close = 7400.5, latest date = 2026-06-05
LATEST_DATE = datetime(2026, 6, 5)
LATEST_CLOSE = 7400.5

# Historical OHLC extracted from the MD calibration logs
HIST_DATA = [
    # date, open, high, low, close
    ("2026-06-01", 7595.0, 7632.2, 7576.2, 7613.2),
    ("2026-06-02", 7612.0, 7632.0, 7576.5, 7623.8),
    ("2026-06-03", 7628.0, 7628.5, 7541.8, 7571.8),
    ("2026-06-04", 7539.8, 7611.5, 7524.5, 7601.0),
    ("2026-06-05", 7589.5, 7591.0, 7359.0, 7400.5),
]

import pandas as pd
df = pd.DataFrame(HIST_DATA, columns=["date", "open", "high", "low", "close"])
df["date"] = pd.to_datetime(df["date"])

# ── KEY POINTS (from MD) ──
KEY_POINTS = [
    {"date": "2026-06-01", "price": 7632.2, "label": "ATH 7632", "marker": "*", "color_key": "ATH"},
    {"date": "2026-06-05", "price": 7359.0,  "label": "Day Low\n7359", "marker": "v", "color_key": "B"},
]

# ── SCENARIO A: 回调后继续上行（状态更新后降至 5%，但保留路径） ──
# 概率5%（基本失效），起点 = 6/5 收盘 7400.5
# 路径：6/9 V/J 合相反弹 → 7480-7530 → 6/13-14 测试 MCL → 后续横盘
SCENARIO_A = {
    "label": "A: Rally after V/J (5%)  — Nearly failed",
    "color": "#0e8a6e",
    "points": [
        {"date": "2026-06-05", "price": 7400.5},
        {"date": "2026-06-09", "price": 7505.0,  "label": "V/J Rally\n7505"},
        {"date": "2026-06-13", "price": 7475.0},
        {"date": "2026-06-14", "price": 7450.0,  "label": "2nd Low\n7450"},
        {"date": "2026-06-22", "price": 7560.0},
        {"date": "2026-06-29", "price": 7500.0},
    ]
}

# ── SCENARIO C (main, 90%): 加速修正 ──
# 6/9 V/J 小反弹 7480-7530 → 后续是否守住 MCL 7354 → 6/13-14 二次探底 → 6/26-29 Major Cycle Low
SCENARIO_C = {
    "label": "C: Accelerated Correction (90%)  — Confirmed",
    "color": "#c0392b",
    "points": [
        {"date": "2026-06-05", "price": 7400.5},
        {"date": "2026-06-09", "price": 7480.0,  "label": "V/J Bounce\n7480"},
        {"date": "2026-06-13", "price": 7380.0},
        {"date": "2026-06-14", "price": 7354.0,  "label": "MCL Test\n7354"},
        {"date": "2026-06-22", "price": 7430.0},
        {"date": "2026-06-26", "price": 7400.0},
        {"date": "2026-06-29", "price": 7380.0,  "label": "Major Cycle Low\n7350-7450"},
    ]
}

# ── CRD windows (from MD) ──
CRDS = [
    # (start, end, label, stars)
    (datetime(2026, 6, 26), datetime(2026, 6, 29), "Jun 26-29 *", 1),
]

# ── Solar-Lunar reversal dates (from MD micro section) ──
SOLAR_LUNAR = [
    # (date, bias)
    (datetime(2026, 6, 4),  "High"),  # Solar-Lunar High 158.8* — 6/4 high 7611.5
    (datetime(2026, 6, 9),  "Low"),   # V/J conjunction — possible bottom
    (datetime(2026, 6, 13), "Low"),   # Solar-Lunar Low 140.8* — 6/13-14 low
    (datetime(2026, 6, 14), "Low"),   # 2nd low target
]

# ── Support bands ──
SUPPORTS = [
    {"low": 7354.0, "high": 7354.0, "label": "MCL 7354 (Last Defense)"},
    {"low": 7250.0, "high": 7300.0, "label": "Deep Support 7250-7300"},
]

# ── Resistance lines ──
RESISTANCES = [
    {"level": 7490.0, "label": "TIP 7490 (Broken)"},
    {"level": 7530.0, "label": "Wk Support 7530-7543"},
    {"level": 7632.0, "label": "ATH 7632"},
]

# ── Astro events ──
ASTRO_LABELS = [
    {"date": "2026-06-09", "y_pos": 7700.0, "text": "Venus☌Jupiter\nV/J Conjunction", "color": "#d4a017"},
    {"date": "2026-06-29", "y_pos": 7700.0, "text": "CRD ★\nMajor Cycle\nLow?",        "color": "#2e86c1"},
]

REPORT_DATE = "20260601"
REPORT_TITLE = "Weekly"

# ─────────────────────────── PLOT ────────────────────────────────────────────
BG   = "#FAFAFA"
FG   = "#222222"
C_A   = "#0e8a6e"
C_B   = "#c0392b"   # scenario C uses C_B (red)
C_ATH = "#d4a017"
C_CRD_1 = "#2e86c1"
C_CRD_2 = "#d4a017"
C_CRD_3 = "#c0392b"
C_SL_LOW  = "#0e8a6e"
C_SL_HIGH = "#c0392b"
C_SL_MIX  = "#d4a017"
C_HIST    = "#1a1a1a"
C_HIST_BAND = "#b0b0b0"
C_SUPPORT = "#0e8a6e"
C_RESIST  = "#c0392b"
C_MCL     = "#c0392b"

fig, ax = plt.subplots(figsize=(28, 10.5))
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)

# X range: historical start -1 day to scenario end +2 days
X_START = datetime(2026, 5, 31)
X_END   = datetime(2026, 7, 1)

# Y range
all_prices = (
    list(df["low"]) + list(df["high"])
    + [p["price"] for p in SCENARIO_A["points"]]
    + [p["price"] for p in SCENARIO_C["points"]]
    + [s["low"] for s in SUPPORTS]
    + [r["level"] for r in RESISTANCES]
)
Y_MIN = min(all_prices) - 120
Y_MAX = max(all_prices) + 180

CRD_LABEL_Y  = Y_MAX - 30
SL_MARKER_Y  = Y_MAX + 20
SL_TEXT_Y    = Y_MAX + 45
ASTRO_Y_BASE = Y_MAX - 80

# ── CRD bands ──
for start, end, label, stars in CRDS:
    alpha = 0.06 + stars * 0.03
    c = C_CRD_3 if stars >= 3 else C_CRD_2 if stars >= 2 else C_CRD_1
    ax.axvspan(start - timedelta(hours=12), end + timedelta(hours=12),
               alpha=alpha, color=c, zorder=0)
    mid = start + (end - start) / 2
    ax.text(mid, CRD_LABEL_Y, label, ha="center", va="top", fontsize=16,
            color=c, fontweight="bold", alpha=0.85)

# ── Support bands ──
for s in SUPPORTS:
    lo, hi = s["low"], s["high"]
    mid = (lo + hi) / 2
    if abs(hi - lo) < 5:
        # single line level
        ax.axhline(y=mid, color=C_SUPPORT, ls="--", lw=1.2, alpha=0.6, zorder=1)
        ax.text(X_END, mid + 4, s["label"], fontsize=13, color=C_SUPPORT,
                alpha=0.8, va="bottom", ha="right")
    else:
        ax.axhspan(lo, hi, alpha=0.08, color=C_SUPPORT, zorder=0)
        ax.axhline(y=mid, color=C_SUPPORT, ls=":", lw=0.7, alpha=0.5)
        ax.text(X_END, mid + 4, s["label"], fontsize=13, color=C_SUPPORT,
                alpha=0.8, va="bottom", ha="right")

# ── Resistance lines ──
for r in RESISTANCES:
    if r["level"] == 7490.0:
        # broken TIP — dashed gray
        ax.axhline(y=r["level"], color="#999999", ls="--", lw=0.9, alpha=0.55)
        ax.text(X_END, r["level"] + 4, r["label"], fontsize=13,
                color="#999999", alpha=0.75, va="bottom", ha="right")
    else:
        ax.axhline(y=r["level"], color=C_RESIST, ls="--", lw=0.8, alpha=0.45)
        ax.text(X_END, r["level"] + 4, r["label"], fontsize=14,
                color=C_RESIST, alpha=0.75, va="bottom", ha="right")

# ── Solar-Lunar markers (above chart) ──
for dt, bias in SOLAR_LUNAR:
    if bias == "Low":
        c, mk = C_SL_LOW, "v"
    elif bias == "High":
        c, mk = C_SL_HIGH, "^"
    else:
        c, mk = C_SL_MIX, "D"
    ax.axvline(x=dt, color=c, ls=":", lw=0.5, alpha=0.2)
    ax.plot(dt, SL_MARKER_Y, marker=mk, color=c, ms=12, zorder=5,
            alpha=0.75, clip_on=False)
    ax.text(dt, SL_TEXT_Y, f"S/L {bias}", ha="center", va="bottom", fontsize=14,
            color=c, alpha=0.7, clip_on=False, fontweight="medium")

# ── Historical H-L band ──
ax.fill_between(df["date"], df["low"], df["high"], alpha=0.10,
                color=C_HIST_BAND, zorder=1, linewidth=0)

# ── Historical close line ──
ax.plot(df["date"], df["close"], color=C_HIST, lw=2.5, zorder=3,
        solid_capstyle="round", label="ES Close (actual, from MD logs)")

# ── Monday vertical lines ──
cur = X_START
while cur <= X_END:
    if cur.weekday() == 0:
        ax.axvline(x=cur, color="#999999", lw=0.6, alpha=0.25, zorder=0)
    cur += timedelta(days=1)

# ── Scenario A path ──
sa_dates  = [datetime.strptime(p["date"], "%Y-%m-%d") for p in SCENARIO_A["points"]]
sa_prices = [p["price"] for p in SCENARIO_A["points"]]
ax.plot(sa_dates, sa_prices, color=C_A, lw=2.5, ls="--", zorder=4,
        marker="o", ms=6, label=SCENARIO_A["label"])
for p in SCENARIO_A["points"]:
    if "label" in p:
        dt = datetime.strptime(p["date"], "%Y-%m-%d")
        ax.annotate(p["label"], (dt, p["price"]), xytext=(14, 16),
                    textcoords="offset points", fontsize=15, color=C_A,
                    fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.2", fc=BG, ec="none", alpha=0.7),
                    arrowprops=dict(arrowstyle="->", color=C_A, lw=0.6))

# ── Scenario C path (main, 90%) ──
sc_dates  = [datetime.strptime(p["date"], "%Y-%m-%d") for p in SCENARIO_C["points"]]
sc_prices = [p["price"] for p in SCENARIO_C["points"]]
ax.plot(sc_dates, sc_prices, color=C_B, lw=2.5, ls="--", zorder=4,
        marker="s", ms=6, label=SCENARIO_C["label"])
for p in SCENARIO_C["points"]:
    if "label" in p:
        dt = datetime.strptime(p["date"], "%Y-%m-%d")
        ax.annotate(p["label"], (dt, p["price"]), xytext=(-50, -30),
                    textcoords="offset points", fontsize=15, color=C_B,
                    fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.2", fc=BG, ec="none", alpha=0.7),
                    arrowprops=dict(arrowstyle="->", color=C_B, lw=0.6))

# ── Key points ──
color_map = {"ATH": C_ATH, "B": C_B, "A": C_A}
for kp in KEY_POINTS:
    dt = datetime.strptime(kp["date"], "%Y-%m-%d")
    c  = color_map.get(kp["color_key"], FG)
    ax.plot(dt, kp["price"], marker=kp["marker"], color=c,
            ms=18 if kp["marker"] == "*" else 12, zorder=6)
    ax.annotate(kp["label"], (dt, kp["price"]), xytext=(20, 14),
                textcoords="offset points", fontsize=16, color=c,
                fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=c, lw=0.8))

# ── TODAY marker ──
ax.axvline(x=LATEST_DATE, color=FG, lw=0.8, alpha=0.4)
ax.annotate(f"TODAY  {LATEST_CLOSE:.0f}", xy=(LATEST_DATE, LATEST_CLOSE),
            xytext=(16, 35), textcoords="offset points", fontsize=18,
            color=FG, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.4", fc=BG, ec=FG, lw=0.8, alpha=0.9),
            arrowprops=dict(arrowstyle="->", color=FG, lw=0.9))
ax.annotate(u"\u2192 C: Accelerated Correction (6/01\u20136/05+)",
            xy=(LATEST_DATE, LATEST_CLOSE),
            xytext=(16, 10), textcoords="offset points", fontsize=14,
            color=C_B, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.3", fc=BG, ec=C_B, lw=0.6, alpha=0.85))

# ── Astro event labels ──
for ev in ASTRO_LABELS:
    dt = datetime.strptime(ev["date"], "%Y-%m-%d")
    ax.annotate(ev["text"], (dt, ev["y_pos"]), fontsize=14, color=ev["color"],
                ha="center", va="top", alpha=0.85, fontstyle="italic",
                bbox=dict(boxstyle="round,pad=0.2", fc=BG, ec="none", alpha=0.6))

# ── MCL special marker ──
ax.axhline(y=7354.0, color=C_MCL, ls="-.", lw=1.2, alpha=0.55, zorder=2)
ax.text(X_START + timedelta(days=0.2), 7358, "MCL 7354 ← Last Defense",
        fontsize=13, color=C_MCL, fontweight="bold", alpha=0.85, va="bottom")

# ── Axes ──
ax.set_xlim(X_START, X_END)
ax.set_ylim(Y_MIN, Y_MAX + 60)

ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
ax.xaxis.set_major_locator(mdates.DayLocator())
plt.setp(ax.get_xticklabels(), rotation=45, ha="right")

ax.yaxis.set_major_locator(mticker.MultipleLocator(100))
ax.yaxis.set_minor_locator(mticker.MultipleLocator(50))
ax.tick_params(which="major", colors="#555555", labelsize=13, length=5)
ax.tick_params(which="minor", colors="#cccccc", length=3)

fig.canvas.draw()
for label in ax.get_xticklabels():
    txt = label.get_text()
    if txt:
        try:
            dt = datetime.strptime(f"2026/{txt}", "%Y/%m/%d")
            if dt.weekday() >= 5:
                label.set_color("#cccccc")
                label.set_fontsize(10)
            elif dt.weekday() == 0:
                label.set_fontweight("bold")
        except ValueError:
            pass

ax.set_xlabel("Date", color="#555555", fontsize=16)
ax.set_ylabel("ES Futures Price", color="#555555", fontsize=16)
ax.set_title(
    f"MMA {REPORT_TITLE} Scenario Projection \u2014 S&P 500 E-mini (ES)  |  Report: {REPORT_DATE}  |  Final Calibration: 2026-06-06",
    color=FG, fontsize=22, fontweight="bold", pad=25,
)

ax.grid(True, which="major", axis="y", alpha=0.12, color="#888888")
ax.grid(True, which="minor", axis="y", alpha=0.05, color="#aaaaaa")
ax.grid(True, which="major", axis="x", alpha=0.06, color="#aaaaaa")

for spine in ax.spines.values():
    spine.set_color("#cccccc")

leg = ax.legend(loc="upper right", fontsize=15, facecolor=BG, edgecolor="#bbbbbb",
                labelcolor=FG, framealpha=0.95)
leg.get_frame().set_linewidth(0.6)

plt.tight_layout(pad=1.8)

out = OUT_DIR / f"{REPORT_DATE}_scenario_chart.png"
out.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(str(out), dpi=160, facecolor=BG, edgecolor="none")
plt.close()
print(f"Saved: {out}")
