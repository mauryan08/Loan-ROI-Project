"""
src/risk_metrics.py
====================
All portfolio-level and segment-level risk & return calculations.

The core framework used here is the *Expected Loss* model:

    Expected Loss (EL) = PD × LGD

where:
    PD  = Probability of Default   (observed default rate in this dataset)
    LGD = Loss Given Default        (1 − Recovery Rate)

Risk-Adjusted ROI = Average ROI − Expected Loss

This is the same framework used by Basel II/III capital models and
commercial lending desks.
"""

import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Portfolio-level KPIs
# ─────────────────────────────────────────────

def portfolio_kpis(df: pd.DataFrame) -> dict:
    """
    Compute top-level portfolio KPIs returned as a plain dictionary.

    Keys
    ----
    total_funded    : Total principal deployed ($).
    total_return    : Total net profit/loss ($).
    avg_roi         : Mean simple ROI across all loans.
    default_rate    : Fraction of loans that charged off / defaulted.
    risk_adj_roi    : ROI after subtracting expected loss.
    total_loans     : Number of loans in the portfolio.
    avg_int_rate    : Portfolio-weighted average interest rate.
    recovery_rate   : Recovery rate on charged-off loans.
    """
    total_funded = df['funded_amnt'].sum()
    total_return = df['net_return'].sum()
    avg_roi      = df['roi_pct'].mean()
    default_rate = df['is_default'].mean()
    total_loans  = len(df)
    avg_int_rate = df['int_rate'].mean()

    charged_off   = df[df['loan_status'] == 'Charged Off']
    charged_amnt  = charged_off['funded_amnt'].sum()
    recovery_rate = (
        charged_off['recoveries'].sum() / charged_amnt
        if charged_amnt > 0 else 0.0
    )

    lgd           = 1 - recovery_rate
    expected_loss = default_rate * lgd
    risk_adj_roi  = avg_roi - expected_loss

    kpis = dict(
        total_funded  = total_funded,
        total_return  = total_return,
        avg_roi       = avg_roi,
        default_rate  = default_rate,
        risk_adj_roi  = risk_adj_roi,
        total_loans   = total_loans,
        avg_int_rate  = avg_int_rate,
        recovery_rate = recovery_rate,
    )

    logger.info("Portfolio KPIs computed: %d loans, $%.2fB funded, %.2f%% avg ROI.",
                total_loans, total_funded / 1e9, avg_roi * 100)
    return kpis


# ─────────────────────────────────────────────
# Grade-level summary
# ─────────────────────────────────────────────

def grade_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate portfolio metrics by Lending Club credit grade (A–G).

    Columns returned
    ----------------
    grade              : Credit grade.
    loans              : Loan count.
    total_funded       : Total principal ($).
    avg_roi            : Mean simple ROI.
    default_rate       : Fraction of loans that defaulted.
    avg_recovery       : Mean recovery amount per loan ($).
    loss_given_default : 1 − Recovery Rate (at grade level).
    expected_loss      : PD × LGD for this grade.
    risk_adj_roi       : avg_roi − expected_loss.
    portfolio_share    : Fraction of total portfolio funded by this grade.
    """
    summary = df.groupby('grade').agg(
        loans         = ('funded_amnt', 'count'),
        total_funded  = ('funded_amnt', 'sum'),
        avg_roi       = ('roi_pct', 'mean'),
        default_rate  = ('is_default', 'mean'),
        avg_recovery  = ('recoveries', 'mean'),
    ).reset_index()

    # Compute LGD per grade from charged-off loans only
    co = df[df['loan_status'] == 'Charged Off']
    co_recovery = co.groupby('grade')['recoveries'].sum()
    co_funded   = co.groupby('grade')['funded_amnt'].sum()
    grade_recovery_rate = (co_recovery / co_funded).reindex(summary['grade']).fillna(0)

    summary['loss_given_default'] = 1 - grade_recovery_rate.values
    summary['expected_loss']      = summary['default_rate'] * summary['loss_given_default']
    summary['risk_adj_roi']       = summary['avg_roi'] - summary['expected_loss']
    summary['portfolio_share']    = summary['total_funded'] / summary['total_funded'].sum()

    logger.info("Grade summary computed for %d grades.", len(summary))
    return summary


# ─────────────────────────────────────────────
# Rate-bucket summary
# ─────────────────────────────────────────────

def rate_bucket_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate ROI and default metrics by interest-rate quintile bucket.

    Columns returned
    ----------------
    rate_bucket  : Quintile interval (e.g. "(6.0, 10.4]").
    loans        : Loan count in this bucket.
    avg_int_rate : Mean interest rate within the bucket.
    avg_roi      : Mean simple ROI.
    default_rate : Fraction of loans that defaulted.
    """
    rs = df.groupby('rate_bucket', observed=True).agg(
        loans        = ('funded_amnt', 'count'),
        avg_int_rate = ('int_rate', 'mean'),
        avg_roi      = ('roi_pct', 'mean'),
        default_rate = ('is_default', 'mean'),
    ).reset_index()

    logger.info("Rate-bucket summary computed for %d buckets.", len(rs))
    return rs


# ─────────────────────────────────────────────
# Cohort (vintage) summary
# ─────────────────────────────────────────────

def cohort_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate portfolio performance by loan issuance year (vintage).

    Columns returned
    ----------------
    issue_year   : Calendar year loans were issued.
    avg_roi      : Mean simple ROI for that vintage.
    default_rate : Default rate for that vintage.
    total_funded : Total principal funded in that year ($).
    loan_count   : Number of loans issued that year.
    """
    cohort = df.groupby('issue_year').agg(
        avg_roi      = ('roi_pct', 'mean'),
        default_rate = ('is_default', 'mean'),
        total_funded = ('funded_amnt', 'sum'),
        loan_count   = ('funded_amnt', 'count'),
    ).reset_index()

    logger.info("Cohort summary computed for %d vintage years.", len(cohort))
    return cohort


# ─────────────────────────────────────────────
# Insights generation
# ─────────────────────────────────────────────

def generate_insights(kpis: dict, gs: pd.DataFrame,
                      rs: pd.DataFrame, cohort: pd.DataFrame) -> list[str]:
    """
    Derive plain-English insights from the computed summaries.

    Returns a list of insight strings suitable for the report and
    insights.txt export.
    """
    best_grade   = gs.loc[gs['risk_adj_roi'].idxmax()]
    worst_grade  = gs.loc[gs['risk_adj_roi'].idxmin()]
    highest_def  = gs.loc[gs['default_rate'].idxmax()]
    best_bucket  = rs.loc[rs['avg_roi'].idxmax()]
    peak_year    = cohort.loc[cohort['avg_roi'].idxmax(), 'issue_year']

    insights = [
        f"Grade '{best_grade['grade']}' delivers the strongest risk-adjusted return "
        f"({best_grade['risk_adj_roi']:.2%}) after accounting for a "
        f"{best_grade['default_rate']:.1%} default rate. Recommended for portfolio overweight.",

        f"Grade '{worst_grade['grade']}' has the lowest risk-adjusted ROI "
        f"({worst_grade['risk_adj_roi']:.2%}). High nominal yield is fully eroded "
        f"by default losses — avoid or underweight.",

        f"Grade '{highest_def['grade']}' carries the highest default rate "
        f"({highest_def['default_rate']:.1%}). Position sizing must reflect tail-risk exposure.",

        f"The interest-rate sweet spot is bucket '{best_bucket['rate_bucket']}' "
        f"(avg {best_bucket['avg_int_rate']:.1f}%), producing the highest raw ROI "
        f"({best_bucket['avg_roi']:.2%}). Above this band, incremental default "
        f"losses outpace the extra interest income.",

        f"Loans issued in {peak_year} showed the highest average ROI. "
        f"Recent vintages are under-represented due to incomplete loan lifecycles "
        f"— survivorship bias caution applies.",

        f"Portfolio-level risk-adjusted ROI is {kpis['risk_adj_roi']:.2%} "
        f"versus a gross average ROI of {kpis['avg_roi']:.2%}. "
        f"The {kpis['avg_roi'] - kpis['risk_adj_roi']:.2%} spread represents "
        f"the expected-loss drag on portfolio returns.",
    ]

    return insights
