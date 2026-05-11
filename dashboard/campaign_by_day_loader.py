"""
Data loading for Campaign By day tab.

Columns: date, os_type, campaign_name, campaign_id, spend, impressions, clicks,
         backend_orders, backend_gmv, product, cpm, cpc, ctr, cpa_purchase, aov, backend_roi

campaign_id here matches campaign_id in the F值报告 dataset.
"""

import os
import numpy as np
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

COLUMNS = [
    "date", "os_type", "campaign_name", "campaign_id",
    "spend", "impressions", "clicks",
    "backend_orders", "backend_gmv", "product",
    "cpm", "cpc", "ctr", "cpa_purchase", "aov", "backend_roi",
]

DISPLAY_NAMES = {
    "date": "Date",
    "os_type": "OS",
    "campaign_name": "Campaign Name",
    "campaign_id": "Campaign ID",
    "spend": "Spend (USD)",
    "impressions": "Impressions",
    "clicks": "Clicks",
    "backend_orders": "Backend Orders",
    "backend_gmv": "Backend GMV (USD)",
    "product": "Product",
    "cpm": "CPM",
    "cpc": "CPC",
    "ctr": "CTR (%)",
    "cpa_purchase": "CPA Purchase",
    "aov": "AOV (客单价)",
    "backend_roi": "Backend ROI",
}


def load_campaign_data(source: str | None = None) -> tuple[pd.DataFrame, str]:
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
    csvs = sorted(DATA_DIR.glob("dhgate_campaignbyday*.csv"))
    if not csvs:
        raise FileNotFoundError(f"No campaignbyday CSV files found in {DATA_DIR}")
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
# Cleaning
# ---------------------------------------------------------------------------

def _clean_numeric(series: pd.Series) -> pd.Series:
    if series.dtype != object:
        return pd.to_numeric(series, errors="coerce")
    s = series.astype(str).str.strip()
    s = s.str.replace(r"[$,]", "", regex=True)
    s = s.str.replace("%", "", regex=False)
    s = s.replace({"#DIV/0!": np.nan, "#VALUE!": np.nan, "nan": np.nan, "": np.nan, "None": np.nan})
    return pd.to_numeric(s, errors="coerce")


def _clean_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df[df["date"].notna() & ~df["date"].str.strip().isin(["", "Total"])]
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df[df["date"].notna()]

    numeric_cols = ["spend", "impressions", "clicks", "backend_orders", "backend_gmv",
                    "cpm", "cpc", "ctr", "cpa_purchase", "aov", "backend_roi"]
    for col in numeric_cols:
        df[col] = _clean_numeric(df[col])

    df = df[df["spend"].notna()]

    for col in ["os_type", "campaign_name", "campaign_id", "product"]:
        df[col] = df[col].fillna("").str.strip().replace("", None)

    return df.sort_values("date").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Helper: campaign ID → name mapping (for use in other pages)
# ---------------------------------------------------------------------------

def get_campaign_name_map(source: str | None = None) -> dict[str, str]:
    """Returns {campaign_id: campaign_name} for display in filters."""
    df, _ = load_campaign_data(source)
    return (
        df[["campaign_id", "campaign_name"]]
        .dropna()
        .drop_duplicates("campaign_id")
        .set_index("campaign_id")["campaign_name"]
        .to_dict()
    )


# ---------------------------------------------------------------------------
# Future loader stub
# ---------------------------------------------------------------------------

def _load_from_feishu_public() -> tuple[pd.DataFrame, str]:
    from feishu_reader import read_sheet
    import numpy as np
    rows = read_sheet("Campaign By day")
    df = _rows_feishu_to_df(rows)
    return df, "Feishu (public share)"


def _rows_feishu_to_df(rows: list[list]) -> pd.DataFrame:
    import numpy as np
    # Row 0 = headers (skip); rows 1+ = data
    data = rows[1:]
    df = pd.DataFrame(data, columns=COLUMNS)
    # Convert Excel serial date
    df["date"] = df["date"].apply(
        lambda v: pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(v))
        if isinstance(v, (int, float)) and not np.isnan(float(v))
        else pd.to_datetime(v, errors="coerce")
    )
    df = df[df["date"].notna()]
    numeric_cols = ["spend", "impressions", "clicks", "backend_orders", "backend_gmv",
                    "cpm", "cpc", "ctr", "cpa_purchase", "aov", "backend_roi"]
    for col in numeric_cols:
        df[col] = df[col].apply(lambda v: None if isinstance(v, str) else v)
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df[df["spend"].notna()]
    for col in ["os_type", "campaign_name", "campaign_id", "product"]:
        df[col] = df[col].fillna("").astype(str).str.strip().replace("", None)
    return df.sort_values("date").reset_index(drop=True)


def _load_from_feishu_api() -> tuple[pd.DataFrame, str]:
    raise NotImplementedError(
        "Feishu API loader not yet implemented. "
        "Complete Lark app approval + client share, then build this."
    )
