#!/usr/bin/env python3
"""
MMA Scenario Projection Chart — Template
==========================================
Usage:  python plot_mma_scenario_template.py --scenario <path/to/YYYYMMDD_scenario_evolution.md>

The AI fills ONLY the section between  # ── DATA START ──  and  # ── DATA END ──
Everything below DATA END is fixed plotting logic — DO NOT MODIFY.
"""
import argparse
import re
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

# ════════════════════════════════════════════════════════════════════
# ── DATA START ──  (AI fills this section; keep variable names exact)
# ════════════════════════════════════════════════════════════════════

REPORT_DATE = "20260608"          # YYYYMMDD from scenario filename
REPORT_TYPE = "Monthly"           # "Monthly" or "Weekly"

# Scenario A — main scenario (highest probability)
SA_LABEL = "A: Correction → New ATH → Jul Crest  (45%)"
SA_DATES = [
    "2026-06-10", "2026-06-13", "2026-06-17", "2026-06-22",
    "2026-06-29", "2026-07-03", "2026-07-08", "2026-07-10",
    "2026-07-18", "2026-07-23", "2026-07-31",
]
SA_PRICES = [7363.0, 7280, 7500, 7550, 7450, 7400, 7580, 7500, 7750, 7600, 7400]
SA_KEY_LABELS = {1: "Half-primary low", 3: "S/L High", 8: "PRIMARY CREST", 9: "Decline"}

# Scenario B — most likely alternative
SB_LABEL = "B: Deep Correction → Delayed Recovery  (25%)"
SB_DATES = [
    "2026-06-10", "2026-06-14", "2026-06-18", "2026-06-29",
    "2026-07-06", "2026-07-15", "2026-07-20", "2026-07-31",
]
SB_PRICES = [7363.0, 7280, 7450, 7100, 7080, 7400, 7550, 7300]
SB_KEY_LABELS = {3: "Deep low", 4: "Confirmed bottom", 6: "Capped rally"}

# CRD windows: (start_date, end_date, label, stars)  stars: 1/2/3
CRDS = [
    ("2026-06-16", "2026-06-17", "Jun 16-17 *", 1),
    ("2026-06-26", "2026-06-29", "Jun 26-29 *", 1),
    ("2026-07-05", "2026-07-07", "Jul 6 **", 2),
    ("2026-07-17", "2026-07-20", "Jul 17-20 ***", 3),
]

# Solar-Lunar reversal dates: (date, bias)  bias: "Low" / "High" / "H/L"
SOLAR_LUNAR = [
    ("2026-06-13", "Low"),
    ("2026-06-17", "H/L"),
    ("2026-06-22", "High"),
    ("2026-07-02", "Low"),
    ("2026-07-04", "Low"),
    ("2026-07-07", "High"),
    ("2026-07-09", "Low"),
]

# Support bands: (low_price, high_price)
SUPPORTS = [(7250, 7300), (7050, 7150)]

# Resistance lines: (price, label)
RESISTANCES = [(7632.25, "ATH 7632"), (7700, "Target 7700"), (7800, "Target 7800")]

# Key historical markers: (date, price, label, marker_shape, color_key)
#   color_key: "ATH" / "A" / "B"
KEY_POINTS = [
    ("2026-06-01", 7632.25, "ATH 7632", "*", "ATH"),
    ("2026-06-09", 7247.25, "Panic Low\n7247", "v", "B"),
]

# Astro event labels (max 3): (date, y_position, text, color_key)
#   color_key: "CRD_2" (gold) / "CRD_3" (red) / "CRD_1" (blue)
ASTRO_LABELS = [
    ("2026-06-25", 7850, "Sun□Neptune\n83% reversal", "CRD_2"),
    ("2026-07-20", 7820, "Jup☍Pluto\nPrimary Crest?", "CRD_3"),
]

# Current phase label (shown next to TODAY marker)
CURRENT_PHASE = "A: Correction Phase (6/05-6/13)"

# ════════════════════════════════════════════════════════════════════
# ── DATA END ──  (DO NOT MODIFY ANYTHING BELOW THIS LINE)
# ════════════════════════════════════════════════════════════════════

# ── Parse arguments ──────────────────────────────────────────────

parser = argparse.ArgumentParser()
parser.add_argument("--scenario", required=True, help="Path to scenario_evolution.md")
args = parser.parse_args()

scenario_path = Path(args.scenario)


def _validate_scenario_metadata(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"Scenario file not found: {path}")
    if not path.is_file():
        raise SystemExit(f"Scenario path is not a file: {path}")

    text = path.read_text(encoding="utf-8")
    date_match = re.search(r"^#\s+.*?(?:月报|周报).*?(\d{4})-(\d{2})-(\d{2})", text, re.MULTILINE)
    if date_match is None:
        date_match = re.search(r"\*\*报告日期\*\*：\s*(\d{4})-(\d{2})-(\d{2})", text)
    if date_match is None:
        raise SystemExit("Unable to parse report date from scenario file")

    type_match = re.search(r"(月报|周报)", text[:1000])
    if type_match:
        report_type = "Monthly" if type_match.group(1) == "月报" else "Weekly"
    else:
        path_text = str(path).lower()
        if "monthly" in path_text:
            report_type = "Monthly"
        elif "weekly" in path_text:
            report_type = "Weekly"
        else:
            report_type = REPORT_TYPE

    report_date = "".join(date_match.group(i) for i in range(1, 4))
    if report_date != REPORT_DATE or report_type != REPORT_TYPE:
        raise SystemExit(
            "Scenario metadata mismatch: "
            f"file has {report_type} {report_date}, "
            f"script data has {REPORT_TYPE} {REPORT_DATE}"
        )


_validate_scenario_metadata(scenario_path)
out_dir = scenario_path.parent
out_path = out_dir / f"{REPORT_DATE}_scenario_chart.png"

ROOT = Path(__file__).resolve().parent
while not (ROOT / "data").exists() and ROOT != ROOT.parent:
    ROOT = ROOT.parent

# ── Load ES data ─────────────────────────────────────────────────

df = pd.read_csv(ROOT / "data" / "es_daily.csv")
df["date"] = pd.to_datetime(df["date"])

sa_first = pd.to_datetime(SA_DATES[0])
hist_start = sa_first - timedelta(days=30)
df = df[df["date"] >= hist_start].copy().reset_index(drop=True)

latest_close = df.iloc[-1]["close"]
latest_date = df.iloc[-1]["date"]

sa_dates = pd.to_datetime(SA_DATES)
sa_prices_final = [latest_close] + SA_PRICES[1:]
sb_dates = pd.to_datetime(SB_DATES)
sb_prices_final = [latest_close] + SB_PRICES[1:]

# ── Colors ───────────────────────────────────────────────────────

BG, FG = "#FAFAFA", "#222222"
COLORS = {
    "HIST": "#1a1a1a", "HIST_BAND": "#b0b0b0",
    "A": "#0e8a6e", "B": "#c0392b", "ATH": "#d4a017",
    "SUPPORT": "#0e8a6e", "RESIST": "#c0392b",
    "CRD_1": "#2e86c1", "CRD_2": "#d4a017", "CRD_3": "#c0392b",
    "SL_LOW": "#0e8a6e", "SL_HIGH": "#c0392b", "SL_MIX": "#d4a017",
}
SL_MARKERS = {"Low": ("v", "SL_LOW"), "High": ("^", "SL_HIGH"), "H/L": ("D", "SL_MIX")}

# ── Create figure ────────────────────────────────────────────────

fig, ax = plt.subplots(figsize=(28, 10.5))
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)

# ── CRD bands ────────────────────────────────────────────────────

for s, e, label, stars in CRDS:
    sd, ed = datetime.strptime(s, "%Y-%m-%d"), datetime.strptime(e, "%Y-%m-%d")
    c = COLORS[f"CRD_{min(stars, 3)}"]
    ax.axvspan(sd - timedelta(hours=12), ed + timedelta(hours=12),
               alpha=0.06 + stars * 0.03, color=c, zorder=0)
    ax.text(sd + (ed - sd) / 2, 0.97, label, transform=ax.get_xaxis_transform(),
            ha="center", va="top", fontsize=16, color=c, fontweight="bold", alpha=0.85)

# ── Support bands ────────────────────────────────────────────────

for lo, hi in SUPPORTS:
    ax.axhspan(lo, hi, alpha=0.08, color=COLORS["SUPPORT"], zorder=0)
    ax.axhline(y=(lo + hi) / 2, color=COLORS["SUPPORT"], ls=":", lw=0.5, alpha=0.5)

# ── Resistance lines ─────────────────────────────────────────────

for level, label in RESISTANCES:
    ax.axhline(y=level, color=COLORS["RESIST"], ls="--", lw=0.8, alpha=0.45)

# ── Solar-Lunar markers ─────────────────────────────────────────

for d, bias in SOLAR_LUNAR:
    dt = datetime.strptime(d, "%Y-%m-%d")
    mk, ck = SL_MARKERS.get(bias, ("D", "SL_MIX"))
    c = COLORS[ck]
    ax.axvline(x=dt, color=c, ls=":", lw=0.5, alpha=0.2)
    ax.plot(dt, 1.04, marker=mk, color=c, ms=12, zorder=5, alpha=0.75,
            clip_on=False, transform=ax.get_xaxis_transform())
    ax.text(dt, 1.07, f"S/L {bias}", ha="center", va="bottom", fontsize=14,
            color=c, alpha=0.7, clip_on=False, fontweight="medium",
            transform=ax.get_xaxis_transform())

# ── Historical ───────────────────────────────────────────────────

ax.fill_between(df["date"], df["low"], df["high"], alpha=0.10,
                color=COLORS["HIST_BAND"], zorder=1, linewidth=0)
ax.plot(df["date"], df["close"], color=COLORS["HIST"], lw=2.5, zorder=3,
        solid_capstyle="round", label="ES Close (actual)")

# ── TODAY marker + current phase ─────────────────────────────────

ax.axvline(x=latest_date, color=FG, lw=0.8, alpha=0.25)
ax.annotate(f"TODAY  {latest_close:.0f}", xy=(latest_date, latest_close),
            xytext=(16, -35), textcoords="offset points", fontsize=18,
            color=FG, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.4", fc=BG, ec=FG, lw=0.8, alpha=0.9),
            arrowprops=dict(arrowstyle="->", color=FG, lw=0.9))
ax.annotate(f"\u2192 {CURRENT_PHASE}", xy=(latest_date, latest_close),
            xytext=(16, -60), textcoords="offset points", fontsize=14,
            color=COLORS["A"], fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.3", fc=BG, ec=COLORS["A"], lw=0.6, alpha=0.85))

# ── Scenario A line ──────────────────────────────────────────────

ax.plot(sa_dates, sa_prices_final, color=COLORS["A"], lw=2.5, ls="--", zorder=4,
        marker="o", ms=6, label=SA_LABEL)
for i, (d, p) in enumerate(zip(sa_dates, sa_prices_final)):
    if i in SA_KEY_LABELS:
        above = p > (min(sa_prices_final) + max(sa_prices_final)) / 2
        oy = 20 if above else -25
        ax.annotate(f"{p:.0f}", (d, p), xytext=(14, oy), textcoords="offset points",
                    fontsize=16, color=COLORS["A"], fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.2", fc=BG, ec="none", alpha=0.7),
                    arrowprops=dict(arrowstyle="->", color=COLORS["A"], lw=0.6))

# ── Scenario B line ──────────────────────────────────────────────

ax.plot(sb_dates, sb_prices_final, color=COLORS["B"], lw=2, ls="--", zorder=4,
        marker="s", ms=5, label=SB_LABEL)
for i, (d, p) in enumerate(zip(sb_dates, sb_prices_final)):
    if i in SB_KEY_LABELS:
        above = p > (min(sb_prices_final) + max(sb_prices_final)) / 2
        oy = 18 if above else -22
        ax.annotate(f"{p:.0f}", (d, p), xytext=(16, oy), textcoords="offset points",
                    fontsize=16, color=COLORS["B"], fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.2", fc=BG, ec="none", alpha=0.7),
                    arrowprops=dict(arrowstyle="->", color=COLORS["B"], lw=0.6))

# ── Key historical markers ──────────────────────────────────────

MARKER_SIZE = {"*": 20, "v": 12, "^": 12, "o": 10}
for d, price, label, mk, ck in KEY_POINTS:
    dt = datetime.strptime(d, "%Y-%m-%d")
    c = COLORS[ck]
    ax.plot(dt, price, marker=mk, color=c, ms=MARKER_SIZE.get(mk, 10), zorder=6)
    above = mk == "*"
    oy = 18 if above else -35
    ax.annotate(label, (dt, price), xytext=(20 if above else -40, oy),
                textcoords="offset points", fontsize=18 if mk == "*" else 16,
                color=c, fontweight="bold", ha="center" if not above else "left",
                arrowprops=dict(arrowstyle="->", color=c, lw=0.8))

# ── Astro event labels ──────────────────────────────────────────

for d, y, text, ck in ASTRO_LABELS:
    dt = datetime.strptime(d, "%Y-%m-%d")
    c = COLORS[ck]
    bold = "bold" if ck == "CRD_3" else "normal"
    ax.annotate(text, (dt, y), fontsize=14, color=c, ha="center", va="top",
                alpha=0.9, fontstyle="italic", fontweight=bold)

# ── Resistance labels (right side) ──────────────────────────────

x_right = ax.get_xlim()[1]
x_right_dt = mdates.num2date(x_right)
for level, label in RESISTANCES:
    ax.text(x_right_dt, level + 5, label, fontsize=14, color=COLORS["RESIST"],
            alpha=0.75, va="bottom", ha="right")

# ── Axes formatting ──────────────────────────────────────────────

all_prices = list(df["low"]) + list(df["high"]) + sa_prices_final + sb_prices_final
all_prices += [s[0] for s in SUPPORTS] + [s[1] for s in SUPPORTS]
all_prices += [r[0] for r in RESISTANCES]
y_min = int((min(all_prices) - 100) / 50) * 50
y_max = int((max(all_prices) + 150) / 50) * 50 + 50

all_dates_raw = list(df["date"]) + list(sa_dates) + list(sb_dates)
x_min = min(all_dates_raw) - timedelta(days=1)
x_max = max(all_dates_raw) + timedelta(days=2)

ax.set_xlim(x_min, x_max)
ax.set_ylim(y_min, y_max)
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
    f"MMA {REPORT_TYPE} Scenario Projection \u2014 S&P 500 E-mini (ES)  |  {REPORT_DATE[:4]}-{REPORT_DATE[4:6]}-{REPORT_DATE[6:]}",
    color=FG, fontsize=22, fontweight="bold", pad=25,
)

# ── Grid + Monday lines ─────────────────────────────────────────

ax.grid(True, which="major", axis="y", alpha=0.12, color="#888888")
ax.grid(True, which="minor", axis="y", alpha=0.05, color="#aaaaaa")
ax.grid(True, which="major", axis="x", alpha=0.06, color="#aaaaaa")

d = x_min
while d <= x_max:
    if d.weekday() == 0:
        ax.axvline(x=d, color="#999999", lw=0.6, alpha=0.25, zorder=0)
    d += timedelta(days=1)

for spine in ax.spines.values():
    spine.set_color("#cccccc")

# ── Legend ────────────────────────────────────────────────────────

leg = ax.legend(loc="upper left", fontsize=16, facecolor=BG, edgecolor="#bbbbbb",
                labelcolor=FG, framealpha=0.95)
leg.get_frame().set_linewidth(0.6)

# ── Save ─────────────────────────────────────────────────────────

plt.tight_layout(pad=1.8)
fig.savefig(str(out_path), dpi=160, facecolor=BG, edgecolor="none")
plt.close()
print(f"Saved: {out_path}")
