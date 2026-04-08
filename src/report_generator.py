"""
src/report_generator.py
========================
Generates all non-dashboard output files:

    reports/
    ├── portfolio_report.pdf       ← 5-page executive PDF
    ├── grade_summary.csv
    ├── rate_bucket_summary.csv
    ├── cohort_summary.csv
    ├── portfolio_metrics.json
    └── insights.txt

The PDF is built with matplotlib's PDF backend — no extra library required.
Each page is a styled figure saved into the same multi-page PDF.

NOTE for the user
-----------------
If you want richer PDF formatting (tables of contents, page numbers in the
footer, hyperlinks) you can install 'reportlab' or 'fpdf2' and extend this
module. The current implementation uses only matplotlib so there are zero
additional dependencies.
"""

import json
import logging
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.ticker as mticker
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.lines import Line2D
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# Reuse the same colour constants — import from dashboard so there's one source of truth
from src.dashboard_builder import (
    BG, PANEL, BORDER, CYAN, AMBER, GREEN, RED, WHITE, GREY, DIMGREY,
    _apply_bloomberg_style, _pct_fmt, _dollar_fmt,
)


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _page_header(fig, page_title: str, page_num: int, total_pages: int = 5):
    """Draw a consistent header + footer on any PDF page figure."""
    fig.text(0.5, 0.97,
             "CREDIT PORTFOLIO PROFITABILITY & RISK ANALYSIS",
             ha='center', color=CYAN, fontsize=12, fontweight='bold',
             fontfamily='monospace')
    fig.text(0.5, 0.955,
             page_title,
             ha='center', color=GREY, fontsize=9, fontfamily='monospace')
    fig.add_artist(plt.Line2D([0.04, 0.96], [0.948, 0.948],
                               color=BORDER, linewidth=0.8,
                               transform=fig.transFigure))
    # Footer
    fig.text(0.5, 0.018,
             f"CONFIDENTIAL  ·  PAGE {page_num} OF {total_pages}  ·  "
             "Credit Portfolio Analytics Pipeline",
             ha='center', color=DIMGREY, fontsize=7, fontfamily='monospace')
    fig.add_artist(plt.Line2D([0.04, 0.96], [0.028, 0.028],
                               color=BORDER, linewidth=0.5,
                               transform=fig.transFigure))


def _section_title(ax, text: str):
    """Write a Bloomberg-style section label inside an axes."""
    ax.text(0, 1.06, text, transform=ax.transAxes,
            color=CYAN, fontsize=9, fontweight='bold',
            fontfamily='monospace', va='bottom')


# ─────────────────────────────────────────────────────────────
# PDF PAGES
# ─────────────────────────────────────────────────────────────

def _page_executive_summary(pdf: PdfPages, kpis: dict,
                             gs: pd.DataFrame, insights: list[str]):
    """Page 1 — Executive Summary: KPIs + top-level prose insights."""
    fig = plt.figure(figsize=(11, 8.5))
    fig.patch.set_facecolor(BG)
    _page_header(fig, "PAGE 1  ·  EXECUTIVE SUMMARY", 1)

    outer = gridspec.GridSpec(2, 1, figure=fig,
                              top=0.93, bottom=0.06,
                              left=0.06, right=0.96,
                              hspace=0.45,
                              height_ratios=[1, 2.5])

    # ── KPI strip ────────────────────────────────────────────────────────────
    kpi_gs   = gridspec.GridSpecFromSubplotSpec(1, 4, subplot_spec=outer[0], wspace=0.12)
    kpi_axes = [fig.add_subplot(kpi_gs[0, i]) for i in range(4)]

    from src.dashboard_builder import _kpi_card
    kpi_specs = [
        ("Portfolio Size",
         f"${kpis['total_funded']/1e9:.2f}B", "", CYAN),
        ("Net Return",
         f"${kpis['total_return']/1e6:.1f}M",
         "Gross P&L",
         GREEN if kpis['total_return'] >= 0 else RED),
        ("Avg ROI",
         f"{kpis['avg_roi']:.2%}", "", GREEN),
        ("Default Rate",
         f"{kpis['default_rate']:.2%}", "", RED),
    ]
    for ax, (lbl, val, sub, col) in zip(kpi_axes, kpi_specs):
        _kpi_card(ax, lbl, val, sub, col)

    # ── Insights text block ───────────────────────────────────────────────────
    ax_txt = fig.add_subplot(outer[1])
    ax_txt.set_facecolor(PANEL)
    for spine in ax_txt.spines.values():
        spine.set_edgecolor(BORDER)
    ax_txt.set_xticks([])
    ax_txt.set_yticks([])
    _section_title(ax_txt, "KEY INSIGHTS")

    y = 0.93
    for i, insight in enumerate(insights, 1):
        # Wrap long lines
        words  = insight.split()
        line   = ""
        lines  = []
        for w in words:
            if len(line) + len(w) + 1 <= 95:
                line = (line + " " + w).strip()
            else:
                lines.append(line)
                line = w
        lines.append(line)

        ax_txt.text(0.02, y, f"{i}.", transform=ax_txt.transAxes,
                    color=AMBER, fontsize=8, fontweight='bold', va='top',
                    fontfamily='monospace')
        for j, ln in enumerate(lines):
            ax_txt.text(0.055, y - j * 0.062, ln, transform=ax_txt.transAxes,
                        color=WHITE, fontsize=8, va='top')
        y -= (len(lines) * 0.062 + 0.04)
        if y < 0.04:
            break

    pdf.savefig(fig, facecolor=BG)
    plt.close(fig)
    logger.info("PDF page 1 (executive summary) written.")


def _page_risk_profile(pdf: PdfPages, gs: pd.DataFrame):
    """Page 2 — Portfolio Risk Profile: default rate + expected loss."""
    fig, axes = plt.subplots(1, 2, figsize=(11, 8.5))
    fig.patch.set_facecolor(BG)
    _page_header(fig, "PAGE 2  ·  PORTFOLIO RISK PROFILE", 2)
    fig.subplots_adjust(top=0.90, bottom=0.10, left=0.08, right=0.96, wspace=0.35)

    grades = gs['grade'].tolist()

    # Default rate bars
    norm   = plt.Normalize(min(gs['default_rate']), max(gs['default_rate']))
    colors = plt.cm.YlOrRd(norm(gs['default_rate']))
    axes[0].bar(grades, gs['default_rate'], color=colors, edgecolor='none', width=0.55)
    for g, v in zip(grades, gs['default_rate']):
        axes[0].text(grades.index(g), v + 0.004, f"{v:.1%}",
                     ha='center', va='bottom', color=WHITE,
                     fontsize=8, fontfamily='monospace')
    axes[0].yaxis.set_major_formatter(mticker.FuncFormatter(_pct_fmt))
    _apply_bloomberg_style(axes[0], "DEFAULT RATE BY GRADE", "Grade", "Default Rate")

    # Expected loss stacked bar
    axes[1].bar(grades, gs['expected_loss'], color=RED,
                edgecolor='none', width=0.55, label='Expected Loss')
    axes[1].bar(grades, gs['risk_adj_roi'], bottom=gs['expected_loss'],
                color=GREEN, edgecolor='none', width=0.55,
                label='Risk-Adj ROI')
    axes[1].yaxis.set_major_formatter(mticker.FuncFormatter(_pct_fmt))
    axes[1].axhline(0, color=BORDER, linewidth=0.8)
    axes[1].legend(fontsize=8, labelcolor=WHITE,
                   facecolor=PANEL, edgecolor=BORDER)
    _apply_bloomberg_style(axes[1],
                           "EXPECTED LOSS vs RISK-ADJ ROI  ◆  PD×LGD Model",
                           "Grade", "Rate")

    pdf.savefig(fig, facecolor=BG)
    plt.close(fig)
    logger.info("PDF page 2 (risk profile) written.")


def _page_risk_return(pdf: PdfPages, gs: pd.DataFrame):
    """Page 3 — Risk vs Return bubble chart with annotations."""
    fig, ax = plt.subplots(figsize=(11, 8.5))
    fig.patch.set_facecolor(BG)
    _page_header(fig, "PAGE 3  ·  RISK vs RETURN ANALYSIS", 3)
    fig.subplots_adjust(top=0.88, bottom=0.10, left=0.10, right=0.94)

    bubble_sizes = (gs['total_funded'] / gs['total_funded'].max() * 1000 + 80)
    sc = ax.scatter(
        gs['default_rate'], gs['avg_roi'],
        s=bubble_sizes,
        c=gs['risk_adj_roi'], cmap='RdYlGn',
        edgecolors=BORDER, linewidths=1,
        zorder=5, alpha=0.92
    )
    cbar = fig.colorbar(sc, ax=ax, pad=0.02, shrink=0.8)
    cbar.set_label('Risk-Adj ROI', color=GREY, fontsize=8)
    cbar.ax.yaxis.set_tick_params(labelcolor=GREY, labelsize=8)
    cbar.outline.set_edgecolor(BORDER)
    cbar.ax.yaxis.set_major_formatter(mticker.FuncFormatter(_pct_fmt))

    for _, row in gs.iterrows():
        ax.annotate(row['grade'],
                    (row['default_rate'], row['avg_roi']),
                    fontsize=11, fontweight='bold', color=WHITE,
                    ha='center', va='center', zorder=6)

    ax.axvline(gs['default_rate'].median(), color=DIMGREY, linestyle=':', linewidth=0.9)
    ax.axhline(gs['avg_roi'].median(),       color=DIMGREY, linestyle=':', linewidth=0.9)
    ax.text(0.01, 0.97, "↑ HIGH ROI / LOW DEFAULT\n(Optimal zone)",
            transform=ax.transAxes, color=GREEN,
            fontsize=8, va='top', fontfamily='monospace')

    ax.xaxis.set_major_formatter(mticker.FuncFormatter(_pct_fmt))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_pct_fmt))
    _apply_bloomberg_style(ax, "RISK vs RETURN  ◆  Bubble Size = Portfolio Weight",
                           "Default Rate", "Avg ROI")

    pdf.savefig(fig, facecolor=BG)
    plt.close(fig)
    logger.info("PDF page 3 (risk vs return) written.")


def _page_cohort(pdf: PdfPages, cohort: pd.DataFrame):
    """Page 4 — Cohort / vintage analysis."""
    fig, axes = plt.subplots(1, 2, figsize=(11, 8.5))
    fig.patch.set_facecolor(BG)
    _page_header(fig, "PAGE 4  ·  VINTAGE COHORT ANALYSIS", 4)
    fig.subplots_adjust(top=0.88, bottom=0.10, left=0.08, right=0.96, wspace=0.38)

    years = cohort['issue_year'].tolist()

    # ROI trend
    axes[0].fill_between(years, cohort['avg_roi'], color=CYAN, alpha=0.15)
    axes[0].plot(years, cohort['avg_roi'], color=CYAN, linewidth=2,
                 marker='o', markersize=5)
    axes[0].yaxis.set_major_formatter(mticker.FuncFormatter(_pct_fmt))
    _apply_bloomberg_style(axes[0], "AVG ROI BY ISSUANCE YEAR",
                           "Issue Year", "Avg ROI")

    # Funding volume bars
    bar_colors = plt.cm.Blues(
        np.linspace(0.4, 0.85, len(cohort))
    )
    axes[1].bar(years, cohort['total_funded'] / 1e6,
                color=bar_colors, edgecolor='none', width=0.7)
    axes[1].yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda y, _: f"${y:.0f}M"))
    _apply_bloomberg_style(axes[1], "PORTFOLIO VOLUME BY ISSUANCE YEAR",
                           "Issue Year", "Total Funded ($M)")

    pdf.savefig(fig, facecolor=BG)
    plt.close(fig)
    logger.info("PDF page 4 (cohort analysis) written.")


def _page_recommendations(pdf: PdfPages, gs: pd.DataFrame, insights: list[str]):
    """Page 5 — Strategy & Recommendations."""
    fig = plt.figure(figsize=(11, 8.5))
    fig.patch.set_facecolor(BG)
    _page_header(fig, "PAGE 5  ·  STRATEGIC RECOMMENDATIONS", 5)

    ax = fig.add_axes([0.06, 0.08, 0.88, 0.82])
    ax.set_facecolor(PANEL)
    for spine in ax.spines.values():
        spine.set_edgecolor(BORDER)
    ax.set_xticks([])
    ax.set_yticks([])

    best_grade  = gs.loc[gs['risk_adj_roi'].idxmax(), 'grade']
    worst_grade = gs.loc[gs['risk_adj_roi'].idxmin(), 'grade']

    recs = [
        ("OVERWEIGHT",   f"Grades {best_grade} and adjacent — highest risk-adjusted returns."),
        ("UNDERWEIGHT",  f"Grade {worst_grade} — default losses fully erode yield."),
        ("AVOID",        "Loans with interest rates in the highest quintile bucket "
                         "(incremental default risk exceeds incremental yield)."),
        ("MONITOR",      "Cohort vintages with rising default rates — "
                         "early indicator of macroeconomic stress."),
        ("DIVERSIFY",    "Maintain exposure across at least 3 grade bands "
                         "to reduce idiosyncratic concentration risk."),
        ("AUTOMATE",     "Run this pipeline monthly to catch portfolio drift early. "
                         "Command: python run_analysis.py --data <path>"),
    ]

    colors_map = {
        "OVERWEIGHT": GREEN, "UNDERWEIGHT": AMBER, "AVOID": RED,
        "MONITOR": AMBER,    "DIVERSIFY": CYAN,    "AUTOMATE": CYAN,
    }

    y = 0.90
    ax.text(0.03, y + 0.04, "PORTFOLIO STRATEGY & RECOMMENDATIONS",
            transform=ax.transAxes, color=CYAN, fontsize=10,
            fontweight='bold', fontfamily='monospace')
    y -= 0.02

    for tag, text in recs:
        ax.text(0.03, y, f"● {tag}", transform=ax.transAxes,
                color=colors_map[tag], fontsize=9,
                fontweight='bold', fontfamily='monospace', va='top')
        ax.text(0.22, y, text, transform=ax.transAxes,
                color=WHITE, fontsize=8.5, va='top')
        y -= 0.12

    y -= 0.04
    ax.text(0.03, y, "DATA PIPELINE",
            transform=ax.transAxes, color=CYAN, fontsize=9,
            fontweight='bold', fontfamily='monospace')
    pipeline = [
        "Raw Lending Club CSV",
        "→  data_loader.py        (validation & cleaning)",
        "→  feature_engineering.py (ROI, default flag, rate buckets)",
        "→  risk_metrics.py        (EL model, grade & cohort summaries)",
        "→  dashboard_builder.py   (Bloomberg-style 2-page dashboard)",
        "→  report_generator.py    (PDF report + CSV/JSON exports)",
    ]
    for step in pipeline:
        y -= 0.06
        ax.text(0.05, y, step, transform=ax.transAxes,
                color=GREY, fontsize=8, fontfamily='monospace', va='top')

    pdf.savefig(fig, facecolor=BG)
    plt.close(fig)
    logger.info("PDF page 5 (recommendations) written.")


# ─────────────────────────────────────────────────────────────
# PUBLIC ENTRY POINTS
# ─────────────────────────────────────────────────────────────

def export_pdf(kpis: dict,
               gs: pd.DataFrame,
               rs: pd.DataFrame,
               cohort: pd.DataFrame,
               insights: list[str],
               output_path: Path) -> None:
    """
    Write the full 5-page executive PDF to ``output_path``.

    Parameters
    ----------
    kpis     : Portfolio-level KPI dictionary from risk_metrics.portfolio_kpis.
    gs       : Grade summary DataFrame.
    rs       : Rate-bucket summary DataFrame.
    cohort   : Cohort summary DataFrame.
    insights : List of plain-English insight strings.
    output_path : Destination file path (will create parent dirs).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with PdfPages(output_path) as pdf:
        _page_executive_summary(pdf, kpis, gs, insights)
        _page_risk_profile(pdf, gs)
        _page_risk_return(pdf, gs)
        _page_cohort(pdf, cohort)
        _page_recommendations(pdf, gs, insights)

    logger.info("PDF report saved → %s", output_path)


def export_csv_tables(gs: pd.DataFrame, rs: pd.DataFrame,
                      cohort: pd.DataFrame, reports_dir: Path) -> None:
    """Export grade, rate-bucket, and cohort summaries as CSVs."""
    reports_dir.mkdir(parents=True, exist_ok=True)

    gs.to_csv(reports_dir / "grade_summary.csv", index=False)
    rs.to_csv(reports_dir / "rate_bucket_summary.csv", index=False)
    cohort.to_csv(reports_dir / "cohort_summary.csv", index=False)

    logger.info("CSV tables exported to %s/", reports_dir)


def export_metrics_json(kpis: dict, reports_dir: Path) -> None:
    """Export portfolio KPIs as a machine-readable JSON file."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / "portfolio_metrics.json"

    # Convert numpy types to native Python for JSON serialisation
    safe_kpis = {k: (float(v) if hasattr(v, 'item') else v)
                 for k, v in kpis.items()}

    with open(path, 'w') as f:
        json.dump(safe_kpis, f, indent=2)

    logger.info("Portfolio metrics JSON exported -> %s", path)


def export_insights_txt(insights: list[str], reports_dir: Path) -> None:
    """Export insights as a plain-text file."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / "insights.txt"

    with open(path, 'w') as f:
        f.write("CREDIT PORTFOLIO ANALYSIS — KEY FINDINGS\n")
        f.write("=" * 55 + "\n\n")
        for i, insight in enumerate(insights, 1):
            f.write(f"{i}. {insight}\n\n")

    logger.info("Insights text exported -> %s", path)
