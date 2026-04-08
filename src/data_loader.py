"""
src/data_loader.py
==================
Handles all data ingestion and validation for the credit portfolio pipeline.

Responsibilities:
    - Load raw CSV from disk
    - Validate required columns exist
    - Drop rows with critical missing / invalid values
    - Log every decision so the pipeline is fully auditable
"""

import logging
import pandas as pd
from pathlib import Path

# Module-level logger — inherits config set by the caller (run_analysis.py)
logger = logging.getLogger(__name__)

# Columns that must exist for the pipeline to function
REQUIRED_COLUMNS = [
    'funded_amnt',   # principal lent out
    'total_pymnt',   # total amount repaid (principal + interest)
    'term',          # loan length in months (36 or 60)
    'loan_status',   # e.g. "Fully Paid", "Charged Off", "Default"
    'grade',         # Lending Club credit grade (A–G)
    'int_rate',      # annual interest rate (%)
    'issue_d',       # loan issuance date string (e.g. "Jan-2015")
    'recoveries',    # post-charge-off recovery amount
]

# Loan statuses that count as a loss event
DEFAULT_STATUSES = ['Charged Off', 'Default']


def load_and_validate(path: Path) -> pd.DataFrame:
    """
    Load the cleaned loans CSV and validate data integrity.

    Steps
    -----
    1. Confirm the file exists on disk.
    2. Read it into a DataFrame.
    3. Check all required columns are present.
    4. Drop rows where core financial fields are null or nonsensical.
    5. Report how many rows were dropped and why.

    Parameters
    ----------
    path : Path
        Filesystem path to the cleaned Lending Club CSV.

    Returns
    -------
    pd.DataFrame
        Validated raw loans DataFrame (no feature engineering yet).

    Raises
    ------
    FileNotFoundError
        If the CSV does not exist at ``path``.
    ValueError
        If required columns are missing, or no valid rows remain after cleaning.
    """
    # ── 1. File existence check ──────────────────────────────────────────────
    if not path.exists():
        raise FileNotFoundError(
            f"Data file not found: {path}\n"
            "Place your cleaned Lending Club CSV at this location, "
            "or pass a different path with --data."
        )

    logger.info("Loading dataset from %s", path)
    df = pd.read_csv(path, low_memory=False)
    logger.info("Raw dataset shape: %d rows × %d columns", *df.shape)

    # ── 2. Column validation ─────────────────────────────────────────────────
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        raise ValueError(
            f"The following required columns are missing from the dataset: {missing_cols}\n"
            "Check that you are using the correct file."
        )
    logger.info("All required columns present.")

    # ── 3. Row-level quality filters ─────────────────────────────────────────
    n_before = len(df)

    df = df.dropna(subset=['funded_amnt', 'total_pymnt', 'term', 'loan_status'])
    logger.debug("After dropping nulls in core fields: %d rows", len(df))

    df = df[df['funded_amnt'] > 0]     # can't compute ROI on $0 principal
    df = df[df['term'] > 0]            # can't annualise over 0-month term
    df = df[df['total_pymnt'] >= 0]    # negative repayments are data errors

    n_dropped = n_before - len(df)
    if n_dropped:
        logger.warning(
            "Dropped %d rows (%.1f%%) due to missing or invalid values.",
            n_dropped, 100 * n_dropped / n_before
        )

    if len(df) == 0:
        raise ValueError(
            "No valid rows remain after validation. "
            "Inspect your data source for systematic quality issues."
        )

    logger.info("Validated dataset: %d loans ready for analysis.", len(df))
    return df
