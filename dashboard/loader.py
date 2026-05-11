"""
Data loading abstraction for DHGate dashboard.

DATA_SOURCE env var controls which loader is used:
  csv          — read latest CSV from ../data/ (current)
  feishu_public — fetch from public Feishu share link (interim, not yet implemented)
  feishu_api   — authenticated Feishu API pull (Phase 2, not yet implemented)

All loaders return the same (df, source_label) tuple so the dashboard
never needs to change when the source switches.
"""

import os
import re
import numpy as np
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

# Positional column names — assigned by index, independent of CSV header encoding
COLUMNS = [
    "date",
    "spend",
    "impressions",
    "clicks",
    "d1_purchases",
    "d1_purchase_value",
    "cpm",
    "cpc",
    "ctr",
    "cpa_purchase",
    "d1_roas",
    "aov",
    "backend_orders",
    "backend_gmv",
    "backend_roi",
    "backend_aov",
]

DISPLAY_NAMES = {
    "date": "Date",
    "spend": "Spend (USD)",
    "impressions": "Impressions",
    "clicks": "Clicks",
    "d1_purchases": "D1 Purchases",
    "d1_purchase_value": "D1 Purchase Value (USD)",
    "cpm": "CPM",
    "cpc": "CPC",
    "ctr": "CTR (%)",
    "cpa_purchase": "CPA Purchase",
    "d1_roas": "D1 ROAS",
    "aov": "AOV (客单价)",
    "backend_orders": "Backend Orders",
    "backend_gmv": "Backend GMV (USD)",
    "backend_roi": "Backend ROI",
    "backend_aov": "Backend AOV (USD)",
}


def load_daily_data(source: str | None = None) -> tuple[pd.DataFrame, str]:
    """
    Returns (df, source_label).
    source defaults to DATA_SOURCE env var, then falls back to 'csv'.
    """
    if source is None:
        source = os.getenv("DATA_SOURCE", "csv")

    if source == "csv":
        return _load_from_csv()
    elif source == "feishu_public":
        return _load_from_feishu_public()
    elif source == "feishu_api":
        return _load_from_feishu_api()
    else:
        raise ValueError(f"Unknown DATA_SOURCE: {source!r}")


# ---------------------------------------------------------------------------
# CSV loader
# ---------------------------------------------------------------------------

def _latest_csv() -> Path:
    csvs = sorted(DATA_DIR.glob("dhgate_daily*.csv"))
    if not csvs:
        raise FileNotFoundError(f"No dhgate_daily*.csv files found in {DATA_DIR}")
    return csvs[-1]


def _load_from_csv() -> tuple[pd.DataFrame, str]:
    path = _latest_csv()
    df = pd.read_csv(
        path,
        encoding="utf-8-sig",
        header=0,
        usecols=range(16),
        dtype=str,
    )
    df.columns = COLUMNS
    df = _clean_df(df)
    return df, f"CSV — {path.name}"


# ---------------------------------------------------------------------------
# Shared cleaning
# ---------------------------------------------------------------------------

def _clean_numeric(series: pd.Series) -> pd.Series:
    if series.dtype != object:
        return pd.to_numeric(series, errors="coerce")
    s = series.astype(str).str.strip()
    s = s.str.replace(r"[$,]", "", regex=True)
    s = s.str.replace("%", "", regex=False)
    s = s.replace({"#DIV/0!": np.nan, "nan": np.nan, "": np.nan, "None": np.nan})
    return pd.to_numeric(s, errors="coerce")


def _clean_df(df: pd.DataFrame) -> pd.DataFrame:
    # Drop the summary "Total" row and any rows with no date
    df = df[df["date"].notna() & ~df["date"].str.strip().isin(["", "Total"])]

    # Parse dates — drop anything that doesn't parse (e.g. header artifacts)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df[df["date"].notna()]

    # Clean all numeric columns
    for col in COLUMNS[1:]:
        df[col] = _clean_numeric(df[col])

    # Drop rows with no spend (empty future-dated rows pre-filled by the client)
    df = df[df["spend"].notna()]

    return df.sort_values("date").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Future loaders — swap in when ready, dashboard unchanged
# ---------------------------------------------------------------------------

def _load_from_feishu_public() -> tuple[pd.DataFrame, str]:
    from feishu_reader import read_sheet
    rows = read_sheet("日报")
    df = _rows_feishu_to_df(rows)
    return df, "Feishu (public share)"


def _rows_feishu_to_df(rows: list[list]) -> pd.DataFrame:
    # Row 0 = headers (skip), rows 1+ = data; filter out the "Total" summary row
    data = [r for r in rows[1:] if r[0] != "Total"]
    df = pd.DataFrame(data, columns=COLUMNS)
    df["date"] = df["date"].apply(_excel_date)
    for col in COLUMNS[1:]:
        # Formula errors ("#DIV/0!" etc.) become NaN
        df[col] = df[col].apply(lambda v: None if isinstance(v, str) else v)
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df[df["date"].notna() & df["spend"].notna()]
    return df.sort_values("date").reset_index(drop=True)


def _excel_date(v):
    """Convert an Excel serial date (int/float) to a pandas Timestamp."""
    try:
        if isinstance(v, (int, float)) and not np.isnan(float(v)):
            return pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(v))
    except (TypeError, ValueError, OverflowError):
        pass
    return pd.to_datetime(v, errors="coerce")


def _load_from_feishu_api() -> tuple[pd.DataFrame, str]:
    raise NotImplementedError(
        "Feishu API loader not yet implemented. "
        "Complete Lark app approval + client share, then build this."
    )
