"""
run_analysis.py
================
Main entry point for the Credit Portfolio Analytics Pipeline.

Usage examples
--------------
# Use default data path defined in this file:
    python run_analysis.py

# Override the data path from the command line:
    python run_analysis.py --data path/to/loans.csv

# Save reports to a custom directory:
    python run_analysis.py --data data/loans.csv --output my_reports

What this script does
----------------------
1.  Parse command-line arguments.
2.  Configure logging (INFO level to console, DEBUG to a log file).
3.  Load and validate the dataset.
4.  Engineer all derived features.
5.  Compute portfolio KPIs, grade/rate/cohort summaries.
6.  Generate plain-English insights.
7.  Build and save the 2-page Bloomberg-style dashboard PNGs.
8.  Build and save the 5-page executive PDF report.
9.  Export CSV tables, JSON metrics, and insights.txt.
10. Print a summary to the console.
"""

import argparse
import logging
import sys
from pathlib import Path

# ── src package imports ──────────────────────────────────────────────────────
from src.data_loader        import load_and_validate
from src.feature_engineering import engineer_features
from src.risk_metrics       import (portfolio_kpis, grade_summary,
                                    rate_bucket_summary, cohort_summary,
                                    generate_insights)
from src.dashboard_builder  import build_page1, build_page2
from src.report_generator   import (export_pdf, export_csv_tables,
                                    export_metrics_json, export_insights_txt)


# ═══════════════════════════════════════════════════════
# DEFAULT CONFIGURATION
# Change these if you don't want to pass CLI arguments.
# ═══════════════════════════════════════════════════════
DEFAULT_DATA_PATH   = Path("data/processed/loans_cleaned.csv")
DEFAULT_REPORTS_DIR = Path("reports")


# ═══════════════════════════════════════════════════════
# LOGGING SETUP
# ═══════════════════════════════════════════════════════

def configure_logging(reports_dir: Path) -> None:
    """
    Set up two log handlers:
        - StreamHandler (console): INFO level — shows progress to the user.
        - FileHandler  (log file): DEBUG level — full trace for debugging.

    Using Python's logging module (instead of print) is considered
    best practice in production pipelines because:
        - Log levels let you filter noise.
        - Log files give you a permanent audit trail.
        - Libraries can attach to the same logger automatically.
    """
    reports_dir.mkdir(parents=True, exist_ok=True)
    log_path = reports_dir / "pipeline.log"

    fmt = "%(asctime)s  %(levelname)-8s  %(name)s  —  %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    logging.basicConfig(
        level=logging.DEBUG,
        format=fmt,
        datefmt=datefmt,
        handlers=[
            logging.StreamHandler(sys.stdout),          # console — INFO+
            logging.FileHandler(log_path, mode='w'),    # file    — DEBUG+
        ]
    )

    # Suppress seaborn / matplotlib internal debug noise
    logging.getLogger('matplotlib').setLevel(logging.WARNING)
    logging.getLogger('PIL').setLevel(logging.WARNING)

    # Console handler should only show INFO and above (not DEBUG)
    logging.getLogger().handlers[0].setLevel(logging.INFO)

    logger = logging.getLogger(__name__)
    logger.info("Logging configured. DEBUG log -> %s", log_path)


# ═══════════════════════════════════════════════════════
# CLI ARGUMENT PARSING
# ═══════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.

    argparse is the standard Python library for building CLIs.
    It automatically generates --help documentation.
    """
    parser = argparse.ArgumentParser(
        prog="run_analysis.py",
        description="Credit Portfolio Profitability & Risk Analysis Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_analysis.py
  python run_analysis.py --data data/loans_cleaned.csv
  python run_analysis.py --data data/loans.csv --output my_reports
        """
    )
    parser.add_argument(
        '--data',
        type=Path,
        default=DEFAULT_DATA_PATH,
        help=f"Path to the cleaned Lending Club CSV. Default: {DEFAULT_DATA_PATH}"
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=DEFAULT_REPORTS_DIR,
        help=f"Directory for all report outputs. Default: {DEFAULT_REPORTS_DIR}"
    )
    return parser.parse_args()


# ═══════════════════════════════════════════════════════
# MAIN PIPELINE
# ═══════════════════════════════════════════════════════

def main():
    args = parse_args()
    configure_logging(args.output)

    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("CREDIT PORTFOLIO ANALYTICS PIPELINE  —  STARTED")
    logger.info("=" * 60)
    logger.info("Data path   : %s", args.data)
    logger.info("Output dir  : %s", args.output)

    # ── 1. Load & validate ───────────────────────────────────────────────────
    try:
        df_raw = load_and_validate(args.data)
    except (FileNotFoundError, ValueError) as e:
        logger.error("Pipeline aborted: %s", e)
        sys.exit(1)

    # ── 2. Feature engineering ───────────────────────────────────────────────
    df = engineer_features(df_raw)

    # ── 3. Compute analytics ─────────────────────────────────────────────────
    kpis   = portfolio_kpis(df)
    gs     = grade_summary(df)
    rs     = rate_bucket_summary(df)
    cohort = cohort_summary(df)

    # ── 4. Generate insights ─────────────────────────────────────────────────
    insights = generate_insights(kpis, gs, rs, cohort)

    # ── 5. Console summary ───────────────────────────────────────────────────
    sep = "-" * 50
    print(f"\n{'='*50}")
    print("  PORTFOLIO SUMMARY")
    print(f"{'='*50}")
    print(f"  Total Portfolio :  ${kpis['total_funded']:>15,.0f}")
    print(f"  Net Return      :  ${kpis['total_return']:>15,.0f}")
    print(f"  Average ROI     :  {kpis['avg_roi']:>14.2%}")
    print(f"  Default Rate    :  {kpis['default_rate']:>14.2%}")
    print(f"  Risk-Adj ROI    :  {kpis['risk_adj_roi']:>14.2%}")
    print(f"  Total Loans     :  {kpis['total_loans']:>15,}")
    print(sep)
    print("\n  GRADE BREAKDOWN")
    print(sep)
    print(f"  {'Grade':<7} {'Loans':>8} {'Avg ROI':>10} {'Default%':>10} {'Risk-Adj ROI':>14}")
    print("  " + "-" * 52)
    for _, r in gs.iterrows():
        print(f"  {r['grade']:<7} {r['loans']:>8,} "
              f"{r['avg_roi']:>10.2%} {r['default_rate']:>10.1%} "
              f"{r['risk_adj_roi']:>14.2%}")

    print(f"\n\n  KEY INSIGHTS\n{sep}")
    for i, insight in enumerate(insights, 1):
        # Simple word-wrap at 70 chars
        words, line, out = insight.split(), "", []
        for w in words:
            if len(line) + len(w) + 1 <= 70:
                line = (line + " " + w).strip()
            else:
                out.append(line); line = w
        out.append(line)
        print(f"\n  {i}. {out[0]}")
        for ln in out[1:]:
            print(f"     {ln}")

    print()

    # ── 6. Dashboard PNGs ────────────────────────────────────────────────────
    try:
        build_page1(df, gs, kpis,
                    args.output / "dashboard_page1_overview.png")
        build_page2(df, gs, rs, cohort,
                    args.output / "dashboard_page2_risk.png")
    except Exception as e:
        logger.warning("Dashboard generation failed: %s", e, exc_info=True)

    # ── 7. PDF Report ────────────────────────────────────────────────────────
    try:
        export_pdf(kpis, gs, rs, cohort, insights,
                   args.output / "portfolio_report.pdf")
    except Exception as e:
        logger.warning("PDF export failed: %s", e, exc_info=True)

    # ── 8. CSV / JSON / TXT exports ──────────────────────────────────────────
    try:
        export_csv_tables(gs, rs, cohort, args.output)
        export_metrics_json(kpis, args.output)
        export_insights_txt(insights, args.output)
    except Exception as e:
        logger.warning("Data export failed: %s", e, exc_info=True)

    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE.  All outputs in: %s/", args.output)
    logger.info("=" * 60)
    print(f"\n  All reports saved to: {args.output}/\n")


if __name__ == "__main__":
    main()
