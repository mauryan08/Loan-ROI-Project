"""
src/feature_engineering.py
===========================
Adds all derived columns used by the risk, dashboard, and report modules.

Every column added here is documented inline so analysts can trace exactly
how each metric is constructed from the raw data.
"""

import logging
import pandas as pd
import numpy as np
from src.data_loader import DEFAULT_STATUSES

logger = logging.getLogger(__name__)


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create all analytical columns needed downstream.

    New columns added
    -----------------
    net_return      : Absolute profit / loss per loan in dollars.
    roi_pct         : Simple return on invested capital (decimal).
    term_years      : Loan term converted from months to years.
    annualized_roi  : CAGR-equivalent return over the loan term.
    is_default      : Binary flag — 1 if charged off / defaulted.
    issue_year      : Integer calendar year the loan was issued.
    rate_bucket     : Quintile band of annual interest rate.

    Parameters
    ----------
    df : pd.DataFrame
        Validated raw loans DataFrame from ``load_and_validate``.

    Returns
    -------
    pd.DataFrame
        Copy of ``df`` with new feature columns appended.
    """
    df = df.copy()   # never mutate the caller's DataFrame in place

    # ── Net return ($) ───────────────────────────────────────────────────────
    # How many dollars the lender made (or lost) on each loan.
    # Positive  → borrower paid back more than was lent (interest income).
    # Negative  → borrower defaulted and paid back less than principal.
    df['net_return'] = df['total_pymnt'] - df['funded_amnt']

    # ── Simple ROI (%) ───────────────────────────────────────────────────────
    # Return expressed as a fraction of principal.
    # Formula: (Total Repaid - Principal) / Principal
    df['roi_pct'] = df['net_return'] / df['funded_amnt']

    # ── Term in years ────────────────────────────────────────────────────────
    # Lending Club terms are 36 or 60 months; convert for annualisation.
    df['term_years'] = df['term'] / 12

    # ── Annualised ROI ───────────────────────────────────────────────────────
    # Converts simple ROI into a CAGR so loans of different lengths are
    # comparable. Formula: (1 + ROI)^(1/years) - 1
    df['annualized_roi'] = (1 + df['roi_pct']) ** (1 / df['term_years']) - 1

    # ── Default flag ─────────────────────────────────────────────────────────
    # 1 if the loan ended in a loss event, 0 otherwise.
    # Used to compute default rates and expected-loss metrics.
    df['is_default'] = df['loan_status'].isin(DEFAULT_STATUSES).astype(int)

    # ── Issue year ───────────────────────────────────────────────────────────
    # Extracts just the year from the "Jan-2015" style date string.
    # Used in cohort (vintage) analysis.
    df['issue_year'] = pd.to_datetime(df['issue_d']).dt.year

    # ── Interest-rate quintile buckets ───────────────────────────────────────
    # Divides loans into 5 equally-populated bands by interest rate.
    # Equal-population (qcut) is better than equal-width (cut) here because
    # the rate distribution is right-skewed.
    df['rate_bucket'] = pd.qcut(df['int_rate'], q=5, precision=1)

    logger.info(
        "Feature engineering complete. Columns added: "
        "net_return, roi_pct, term_years, annualized_roi, "
        "is_default, issue_year, rate_bucket."
    )
    return df
