"""
src/dashboard_builder.py
=========================
Builds two Bloomberg-terminal-style dashboard pages and saves them as PNGs.

Page 1 — Portfolio Overview
    KPI ticker strip, ROI by grade, default rate by grade, risk vs return scatter.

Page 2 — Risk & Cohort Deep-Dive
    Expected loss by grade, rate-bucket analysis, cohort trend, ROI heatmap.

Visual design philosophy (Bloomberg terminal):
    - Near-black background with dark panel cards
    - Cyan primary accent, amber secondary, green positive, red negative
    - Tight monospace-inspired typography
    - Dense information layout — every pixel earns its place
    - Thin grid lines, minimal decoration
"""

import logging
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.ticker as mticker
from pathlib import Path

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════
# BLOOMBERG TERMINAL COLOUR PALETTE
# ═══════════════════════════════════════════════════════
BG       = "#0B0F14"   # page / figure background
PANEL    = "#11161C"   # chart / card panel fill
BORDER   = "#2A2F36"   # panel border / grid lines
CYAN     = "#00A3FF"   # primary accent — titles, main bars, lines
AMBER    = "#F5B700"   # secondary accent — overlay lines, highlights
GREEN    = "#00D964"   # positive values
RED      = "#FF3B3B"   # negative / warning values
WHITE    = "#E6EDF3"   # primary text
GREY     = "#8B949E"   # secondary / axis text
DIMGREY  = "#484F58"   # very faint grid / borders


def _apply_bloomberg_style(ax, title="", xlabel="", ylabel=""):
    """
    Apply Bloomberg terminal styling to a single Axes object.

    This helper is called after every chart is drawn so that every panel
    shares identical background, grid, spine, and label colours.
    """
    ax.set_facecolor(PANEL)

    # Spine (box border) colour
    for spine in ax.spines.values():
        spine.set_edgecolor(BORDER)
        spine.set_linewidth(0.8)

    # Tick marks
    ax.tick_params(colors=GREY, labelsize=8, length=3, width=0.8)

    # Axis labels
    ax.xaxis.label.set_color(GREY)
    ax.yaxis.label.set_color(GREY)
    ax.xaxis.label.set_fontsize(8)
    ax.yaxis.label.set_fontsize(8)

    # Horizontal grid only — keeps charts readable without clutter
    ax.grid(axis='y', color=DIMGREY, linestyle='--', linewidth=0.5, alpha=0.8)
    ax.set_axisbelow(True)   # grid renders behind bars/lines

    if title:
        ax.set_title(title, color=CYAN, fontsize=9,
                     fontweight='bold', pad=6, loc='left')
    if xlabel:
        ax.set_xlabel(xlabel, color=GREY, fontsize=8)
    if ylabel:
        ax.set_ylabel(ylabel, color=GREY, fontsize=8)


def _kpi_card(ax, label: str, value: str, sub: str = "",
              value_color: str = CYAN):
    """
    Render a Bloomberg-style KPI card inside a bare Axes.

    Layout (top → bottom):
        ┌──────────────────────┐
        │        VALUE         │  ← large, coloured
        │        label         │  ← small grey
        │         sub          │  ← tiny dim annotation
        └──────────────────────┘
    """
    ax.set_facecolor(PANEL)
    for spine in ax.spines.values():
        spine.set_edgecolor(BORDER)
        spine.set_linewidth(1)
    ax.set_xticks([])
    ax.set_yticks([])

    # Thin top accent line
    from matplotlib.lines import Line2D
    ax.add_line(Line2D([0.1, 0.9], [0.92, 0.92],
                       transform=ax.transAxes,
                       color=value_color, linewidth=1.5))

    ax.text(0.5, 0.64, value, transform=ax.transAxes,
            ha='center', va='center',
            fontsize=20, fontweight='bold', color=value_color,
            fontfamily='monospace')

    ax.text(0.5, 0.32, label.upper(), transform=ax.transAxes,
            ha='center', va='center',
            fontsize=7.5, color=GREY, fontweight='bold',
            fontfamily='monospace')

    if sub:
        ax.text(0.5, 0.12, sub, transform=ax.transAxes,
                ha='center', va='center',
                fontsize=7, color=DIMGREY)


def _pct_fmt(y, _):
    return f"{y:.0%}"


def _dollar_fmt(y, _):
    if abs(y) >= 1e9:
        return f"${y/1e9:.1f}B"
    if abs(y) >= 1e6:
        return f"${y/1e6:.0f}M"
    return f"${y:,.0f}"


# ═══════════════════════════════════════════════════════
# PAGE 1 — PORTFOLIO OVERVIEW
# ═══════════════════════════════════════════════════════

def build_page1(df: pd.DataFrame,
                gs_data: pd.DataFrame,
                kpis: dict,
                output_path: Path) -> None:
    """
    Dashboard Page 1: Portfolio Overview.

    Layout
    ------
    Row 0 (header)    : Title + timestamp strip
    Row 1 (KPI strip) : 6 KPI cards side by side
    Row 2 (charts)    : ROI by Grade | Default Rate by Grade | Risk vs Return
    Row 3 (charts)    : ROI Distribution | Grade Allocation Pie | Summary table
    """
    fig = plt.figure(figsize=(22, 14))
    fig.patch.set_facecolor(BG)

    # ── Header ───────────────────────────────────────────────────────────────
    fig.text(0.5, 0.978,
             "CREDIT PORTFOLIO PERFORMANCE & RISK ANALYSIS  ●  PAGE 1 OF 2",
             ha='center', color=CYAN, fontsize=13, fontweight='bold',
             fontfamily='monospace')
    fig.text(0.5, 0.961,
             "Loan-Level Analytics  |  Grades A–G  |  All Vintages",
             ha='center', color=GREY, fontsize=8, fontfamily='monospace')
    # Horizontal divider under header
    fig.add_artist(plt.Line2D([0.02, 0.98], [0.955, 0.955],
                               color=BORDER, linewidth=0.8,
                               transform=fig.transFigure))

    # ── GridSpec ─────────────────────────────────────────────────────────────
    outer = gridspec.GridSpec(
        3, 1, figure=fig,
        top=0.945, bottom=0.04,
        left=0.04, right=0.98,
        hspace=0.42,
        height_ratios=[0.8, 3, 3]
    )

    # Row 0 — 6 KPI cards
    kpi_gs   = gridspec.GridSpecFromSubplotSpec(1, 6, subplot_spec=outer[0], wspace=0.1)
    kpi_axes = [fig.add_subplot(kpi_gs[0, i]) for i in range(6)]

    # Row 1 — 3 charts
    r1 = gridspec.GridSpecFromSubplotSpec(1, 3, subplot_spec=outer[1], wspace=0.32)
    ax_roi_grade = fig.add_subplot(r1[0, 0])
    ax_def_grade = fig.add_subplot(r1[0, 1])
    ax_scatter   = fig.add_subplot(r1[0, 2])

    # Row 2 — 3 charts
    r2 = gridspec.GridSpecFromSubplotSpec(1, 3, subplot_spec=outer[2], wspace=0.32)
    ax_dist  = fig.add_subplot(r2[0, 0])
    ax_pie   = fig.add_subplot(r2[0, 1])
    ax_table = fig.add_subplot(r2[0, 2])

    # ── KPI CARDS ─────────────────────────────────────────────────────────────
    total_funded = kpis['total_funded']
    total_return = kpis['total_return']

    kpi_specs = [
        ("Total Funded",
         f"${total_funded/1e9:.2f}B",
         "Principal deployed",
         CYAN),
        ("Net Return",
         f"${total_return/1e6:.1f}M",
         "Gross P&L",
         GREEN if total_return >= 0 else RED),
        ("Avg ROI",
         f"{kpis['avg_roi']:.2%}",
         "Simple return",
         GREEN if kpis['avg_roi'] >= 0 else RED),
        ("Default Rate",
         f"{kpis['default_rate']:.2%}",
         "Loss frequency",
         RED),
        ("Avg Int Rate",
         f"{kpis['avg_int_rate']:.1f}%",
         "Portfolio rate",
         AMBER),
        ("Total Loans",
         f"{kpis['total_loans']:,}",
         "Active + settled",
         CYAN),
    ]
    for ax, (lbl, val, sub, col) in zip(kpi_axes, kpi_specs):
        _kpi_card(ax, lbl, val, sub, col)

    # ── CHART 1 — Avg ROI by Grade ────────────────────────────────────────────
    grades    = gs_data['grade'].tolist()
    roi_vals  = gs_data['avg_roi'].tolist()
    bar_cols  = [GREEN if v >= 0 else RED for v in roi_vals]
    bars = ax_roi_grade.bar(grades, roi_vals, color=bar_cols,
                             edgecolor='none', width=0.55)
    for bar, val in zip(bars, roi_vals):
        offset = max(abs(val) * 0.03, 0.003)
        ax_roi_grade.text(
            bar.get_x() + bar.get_width() / 2,
            val + (offset if val >= 0 else -offset - 0.015),
            f"{val:.1%}", ha='center',
            va='bottom' if val >= 0 else 'top',
            color=WHITE, fontsize=7.5, fontfamily='monospace'
        )
    # Overlay: risk-adjusted ROI line
    ax_roi_grade.plot(grades, gs_data['risk_adj_roi'].tolist(),
                      color=AMBER, marker='D', markersize=5,
                      linewidth=1.8, label='Risk-Adj ROI', zorder=5)
    ax_roi_grade.axhline(0, color=BORDER, linewidth=0.8)
    ax_roi_grade.yaxis.set_major_formatter(mticker.FuncFormatter(_pct_fmt))
    ax_roi_grade.legend(fontsize=7, labelcolor=WHITE,
                        facecolor=PANEL, edgecolor=BORDER, loc='upper right')
    _apply_bloomberg_style(ax_roi_grade,
                           title="AVG ROI BY GRADE  ◆  Risk-Adj Overlay",
                           xlabel="Grade", ylabel="ROI")

    # ── CHART 2 — Default Rate by Grade ───────────────────────────────────────
    def_vals   = gs_data['default_rate'].tolist()
    # Sequential blue-to-red: lighter = low risk, darker = high risk
    norm       = plt.Normalize(min(def_vals), max(def_vals))
    def_colors = plt.cm.YlOrRd(norm(def_vals))
    bars2 = ax_def_grade.bar(grades, def_vals, color=def_colors,
                              edgecolor='none', width=0.55)
    for bar, val in zip(bars2, def_vals):
        ax_def_grade.text(
            bar.get_x() + bar.get_width() / 2,
            val + 0.003,
            f"{val:.1%}", ha='center', va='bottom',
            color=WHITE, fontsize=7.5, fontfamily='monospace'
        )
    ax_def_grade.yaxis.set_major_formatter(mticker.FuncFormatter(_pct_fmt))
    _apply_bloomberg_style(ax_def_grade,
                           title="DEFAULT RATE BY GRADE  ◆  YlOrRd Scale",
                           xlabel="Grade", ylabel="Default Rate")

    # ── CHART 3 — Risk vs Return Bubble Scatter ────────────────────────────────
    bubble_sizes = (gs_data['total_funded'] / gs_data['total_funded'].max() * 900 + 80)
    sc = ax_scatter.scatter(
        gs_data['default_rate'], gs_data['avg_roi'],
        s=bubble_sizes,
        c=gs_data['risk_adj_roi'],
        cmap='RdYlGn',
        edgecolors=BORDER, linewidths=0.8,
        zorder=5, alpha=0.92
    )
    cbar = fig.colorbar(sc, ax=ax_scatter, pad=0.02, shrink=0.85)
    cbar.set_label('Risk-Adj ROI', color=GREY, fontsize=7)
    cbar.ax.yaxis.set_tick_params(color=GREY, labelcolor=GREY, labelsize=7)
    cbar.outline.set_edgecolor(BORDER)
    cbar.ax.yaxis.set_major_formatter(mticker.FuncFormatter(_pct_fmt))

    for _, row in gs_data.iterrows():
        ax_scatter.annotate(
            row['grade'],
            (row['default_rate'], row['avg_roi']),
            fontsize=9, fontweight='bold', color=WHITE,
            ha='center', va='center', zorder=6
        )

    # Median quadrant crosshairs
    for med_val, axis in [
        (gs_data['default_rate'].median(), 'x'),
        (gs_data['avg_roi'].median(), 'y')
    ]:
        if axis == 'x':
            ax_scatter.axvline(med_val, color=DIMGREY, linestyle=':', linewidth=0.9)
        else:
            ax_scatter.axhline(med_val, color=DIMGREY, linestyle=':', linewidth=0.9)

    ax_scatter.xaxis.set_major_formatter(mticker.FuncFormatter(_pct_fmt))
    ax_scatter.yaxis.set_major_formatter(mticker.FuncFormatter(_pct_fmt))
    _apply_bloomberg_style(ax_scatter,
                           title="RISK vs RETURN  ◆  Bubble = Portfolio Weight",
                           xlabel="Default Rate (Risk)", ylabel="Avg ROI (Return)")

    # ── CHART 4 — ROI Distribution ────────────────────────────────────────────
    clipped = df['roi_pct'].clip(-0.5, 0.5)
    n, bins, patches = ax_dist.hist(clipped, bins=60, edgecolor='none')
    # Colour bars: green above 0, red below 0
    for patch, left_edge in zip(patches, bins[:-1]):
        patch.set_facecolor(GREEN if left_edge >= 0 else RED)
        patch.set_alpha(0.75)
    ax_dist.axvline(0, color=WHITE, linewidth=0.9, linestyle='--')
    ax_dist.axvline(df['roi_pct'].mean(), color=AMBER, linewidth=1.2,
                    linestyle='--', label=f"Mean {df['roi_pct'].mean():.1%}")
    ax_dist.legend(fontsize=7, labelcolor=WHITE,
                   facecolor=PANEL, edgecolor=BORDER)
    ax_dist.xaxis.set_major_formatter(mticker.FuncFormatter(_pct_fmt))
    _apply_bloomberg_style(ax_dist,
                           title="ROI DISTRIBUTION  ◆  Clipped ±50%",
                           xlabel="ROI", ylabel="Loan Count")

    # ── CHART 5 — Portfolio Allocation Pie ────────────────────────────────────
    ax_pie.set_facecolor(PANEL)
    for spine in ax_pie.spines.values():
        spine.set_edgecolor(BORDER)

    cmap_blues = plt.cm.get_cmap('Blues', len(gs_data) + 2)
    pie_colors = [cmap_blues(i / (len(gs_data) + 1)) for i in range(2, len(gs_data) + 2)]

    wedges, texts, autotexts = ax_pie.pie(
        gs_data['portfolio_share'],
        labels=gs_data['grade'],
        autopct='%1.1f%%',
        colors=pie_colors,
        startangle=90,
        wedgeprops=dict(edgecolor=BG, linewidth=1.5),
        textprops=dict(color=WHITE, fontsize=8)
    )
    for at in autotexts:
        at.set_color(WHITE)
        at.set_fontsize(7)
    ax_pie.set_title("PORTFOLIO ALLOCATION BY GRADE", color=CYAN,
                     fontsize=9, fontweight='bold', pad=6, loc='left')

    # ── CHART 6 — Grade Summary Table ─────────────────────────────────────────
    ax_table.set_facecolor(PANEL)
    for spine in ax_table.spines.values():
        spine.set_visible(False)
    ax_table.set_xticks([])
    ax_table.set_yticks([])
    ax_table.set_title("GRADE METRICS SUMMARY", color=CYAN,
                       fontsize=9, fontweight='bold', pad=6, loc='left')

    cols  = ['Grade', 'Loans', 'Avg ROI', 'Default%', 'Risk-Adj ROI']
    rows  = []
    for _, r in gs_data.iterrows():
        rows.append([
            r['grade'],
            f"{r['loans']:,}",
            f"{r['avg_roi']:.2%}",
            f"{r['default_rate']:.1%}",
            f"{r['risk_adj_roi']:.2%}",
        ])

    table = ax_table.table(
        cellText=rows, colLabels=cols,
        loc='center', cellLoc='center'
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1, 1.8)

    for (row_i, col_i), cell in table.get_celld().items():
        cell.set_facecolor(BG if row_i == 0 else PANEL)
        cell.set_edgecolor(BORDER)
        cell.set_text_props(
            color=CYAN if row_i == 0 else WHITE,
            fontfamily='monospace',
            fontsize=8
        )

    # ── Save Page 1 ──────────────────────────────────────────────────────────
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches='tight',
                facecolor=BG, edgecolor='none')
    plt.close(fig)
    logger.info("Page 1 dashboard saved -> %s", output_path)


# ═══════════════════════════════════════════════════════
# PAGE 2 — RISK & COHORT DEEP-DIVE
# ═══════════════════════════════════════════════════════

def build_page2(df: pd.DataFrame,
                gs_data: pd.DataFrame,
                rs: pd.DataFrame,
                cohort: pd.DataFrame,
                output_path: Path) -> None:
    """
    Dashboard Page 2: Risk & Cohort Deep-Dive.

    Layout
    ------
    Row 0 (header)  : Title strip
    Row 1 (charts)  : Expected Loss by Grade | Rate Bucket grouped bar
    Row 2 (charts)  : Cohort trend dual-axis | ROI Heatmap Grade × Term
    """
    fig = plt.figure(figsize=(22, 14))
    fig.patch.set_facecolor(BG)

    # ── Header ───────────────────────────────────────────────────────────────
    fig.text(0.5, 0.978,
             "CREDIT PORTFOLIO PERFORMANCE & RISK ANALYSIS  ●  PAGE 2 OF 2",
             ha='center', color=CYAN, fontsize=13, fontweight='bold',
             fontfamily='monospace')
    fig.text(0.5, 0.961,
             "Risk Deep-Dive  |  Rate Analysis  |  Vintage Performance  |  Heatmap",
             ha='center', color=GREY, fontsize=8, fontfamily='monospace')
    fig.add_artist(plt.Line2D([0.02, 0.98], [0.955, 0.955],
                               color=BORDER, linewidth=0.8,
                               transform=fig.transFigure))

    # ── GridSpec ─────────────────────────────────────────────────────────────
    outer = gridspec.GridSpec(
        2, 1, figure=fig,
        top=0.945, bottom=0.05,
        left=0.05, right=0.97,
        hspace=0.40
    )

    r1 = gridspec.GridSpecFromSubplotSpec(1, 2, subplot_spec=outer[0], wspace=0.30)
    ax_el     = fig.add_subplot(r1[0, 0])
    ax_rate   = fig.add_subplot(r1[0, 1])

    r2 = gridspec.GridSpecFromSubplotSpec(1, 2, subplot_spec=outer[1], wspace=0.30)
    ax_cohort = fig.add_subplot(r2[0, 0])
    ax_heat   = fig.add_subplot(r2[0, 1])

    # ── CHART 1 — Expected Loss by Grade ──────────────────────────────────────
    grades = gs_data['grade'].tolist()

    x      = np.arange(len(grades))
    width  = 0.28
    ax_el.bar(x - width, gs_data['avg_roi'],          width, color=CYAN,
              edgecolor='none', label='Avg ROI')
    ax_el.bar(x,          gs_data['risk_adj_roi'],     width, color=GREEN,
              edgecolor='none', label='Risk-Adj ROI')
    ax_el.bar(x + width,  gs_data['expected_loss'],   width, color=RED,
              edgecolor='none', label='Expected Loss (PD×LGD)')

    ax_el.set_xticks(x)
    ax_el.set_xticklabels(grades, color=WHITE)
    ax_el.yaxis.set_major_formatter(mticker.FuncFormatter(_pct_fmt))
    ax_el.axhline(0, color=BORDER, linewidth=0.8)
    ax_el.legend(fontsize=7.5, labelcolor=WHITE,
                 facecolor=PANEL, edgecolor=BORDER, loc='upper right')
    _apply_bloomberg_style(ax_el,
                           title="EXPECTED LOSS vs ROI BY GRADE  ◆  PD × LGD Model",
                           xlabel="Grade", ylabel="Rate / ROI")

    # ── CHART 2 — ROI vs Default by Rate Bucket ────────────────────────────────
    labels_r  = [str(b) for b in rs['rate_bucket']]
    x_r       = np.arange(len(labels_r))
    ax_rate.bar(x_r - 0.2, rs['avg_roi'],      0.38, color=CYAN,
                edgecolor='none', label='Avg ROI')
    ax_rate.bar(x_r + 0.2, rs['default_rate'], 0.38, color=RED,
                edgecolor='none', label='Default Rate')
    ax_rate.set_xticks(x_r)
    ax_rate.set_xticklabels(labels_r, rotation=18, ha='right',
                             color=WHITE, fontsize=7.5)
    ax_rate.yaxis.set_major_formatter(mticker.FuncFormatter(_pct_fmt))
    ax_rate.legend(fontsize=7.5, labelcolor=WHITE,
                   facecolor=PANEL, edgecolor=BORDER)
    _apply_bloomberg_style(ax_rate,
                           title="ROI vs DEFAULT RATE BY RATE BUCKET  ◆  Quintiles",
                           xlabel="Rate Quintile", ylabel="Rate")

    # ── CHART 3 — Cohort Trend (dual-axis) ────────────────────────────────────
    years = cohort['issue_year'].tolist()
    c_roi = cohort['avg_roi'].tolist()
    c_def = cohort['default_rate'].tolist()

    ax_cohort.fill_between(years, c_roi, color=CYAN, alpha=0.15)
    ax_cohort.plot(years, c_roi, color=CYAN, linewidth=2,
                   marker='o', markersize=5, label='Avg ROI')
    ax_cohort.yaxis.set_major_formatter(mticker.FuncFormatter(_pct_fmt))
    _apply_bloomberg_style(ax_cohort,
                           title="VINTAGE COHORT PERFORMANCE  ◆  ROI + Default Trend",
                           xlabel="Issue Year", ylabel="Avg ROI")

    ax2 = ax_cohort.twinx()
    ax2.plot(years, c_def, color=RED, linewidth=2,
             linestyle='--', marker='s', markersize=5, label='Default Rate')
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(_pct_fmt))
    ax2.tick_params(colors=RED, labelsize=8, length=3)
    ax2.set_facecolor(PANEL)
    for spine in ax2.spines.values():
        spine.set_edgecolor(BORDER)
    ax2.set_ylabel("Default Rate", color=RED, fontsize=8)

    h1, l1 = ax_cohort.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax_cohort.legend(h1 + h2, l1 + l2, fontsize=7.5, labelcolor=WHITE,
                     facecolor=PANEL, edgecolor=BORDER)

    # ── CHART 4 — ROI Heatmap Grade × Term ────────────────────────────────────
    import seaborn as sns   # local import — only needed for heatmap

    pivot = df.pivot_table(values='roi_pct', index='grade',
                           columns='term', aggfunc='mean')

    _fmt_fn = lambda v: f"{v:.1%}" if pd.notna(v) else ""
    try:
        annot = pivot.map(_fmt_fn)
    except AttributeError:
        annot = pivot.applymap(_fmt_fn)

    sns.heatmap(
        pivot, ax=ax_heat,
        cmap='Blues',
        linewidths=0.4, linecolor=BG,
        annot=annot, fmt='',
        annot_kws=dict(size=9, color=WHITE, fontweight='bold',
                       fontfamily='monospace'),
        cbar_kws=dict(shrink=0.7, pad=0.02)
    )
    ax_heat.set_facecolor(PANEL)
    ax_heat.set_title("ROI HEATMAP  ◆  Grade × Loan Term (months)",
                      color=CYAN, fontsize=9, fontweight='bold',
                      pad=6, loc='left')
    ax_heat.tick_params(colors=GREY, labelsize=9)
    ax_heat.set_xlabel("Loan Term (months)", color=GREY, fontsize=8)
    ax_heat.set_ylabel("Grade", color=GREY, fontsize=8)
    cbar_h = ax_heat.collections[0].colorbar
    cbar_h.ax.yaxis.set_tick_params(color=GREY, labelcolor=GREY, labelsize=7)
    cbar_h.outline.set_edgecolor(BORDER)
    cbar_h.ax.yaxis.set_major_formatter(mticker.FuncFormatter(_pct_fmt))

    # ── Save Page 2 ──────────────────────────────────────────────────────────
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches='tight',
                facecolor=BG, edgecolor='none')
    plt.close(fig)
    logger.info("Page 2 dashboard saved -> %s", output_path)
