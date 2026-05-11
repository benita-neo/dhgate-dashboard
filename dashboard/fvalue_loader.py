"""
Data loading for F值报告 (creative-level report) tab.

Same abstraction as loader.py: DATA_SOURCE env var selects the backend.
All loaders return (df, source_label) — the page never changes when source switches.

f_value string format: bm|moloco|{campaign_id}|{format}|{app_id}|{app_name}|{creative_type}|
Edge cases handled:
  - app_name may contain | (e.g. "Flightradar24 | Flight Tracker") — parsed from the end
  - "BF" tag prefix before campaign_id for Black Friday creatives
  - Incomplete strings with fewer segments (campaign_id only, no metadata)

Note: position 2 of the f_value string is the campaign ID (same ID as in Campaign By day sheet).
The client labels this column "Campaign ID（公式获取）".
"""

import os
import numpy as np
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

# Creative types that appear as the last segment when present
_CREATIVE_TYPES = {"video", "image", "playable", "native", "html", "endcard"}

# Cleaned column names
FVALUE_RAW_COLS = [
    "date", "channel", "sub_channel", "site", "os_type", "country",
    "f_value", "nb_users", "nb_orders", "nb_gmv", "ab_users", "ab_orders", "ab_gmv",
]

DISPLAY_NAMES = {
    "date": "Date",
    "country": "Country",
    "os_type": "OS",
    "campaign_id": "Campaign ID",
    "format": "Format",
    "app_id": "App ID",
    "app_name": "App Name",
    "creative_type": "Creative Type",
    "nb_users": "NB Users",
    "nb_orders": "NB Orders",
    "nb_gmv": "NB GMV (USD)",
    "ab_users": "AB Users",
    "ab_orders": "AB Orders",
    "ab_gmv": "AB GMV (USD)",
}


def load_fvalue_data(source: str | None = None) -> tuple[pd.DataFrame, str]:
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

def _latest_fvalue_csv() -> Path:
    csvs = sorted(DATA_DIR.glob("dhgate_fvalue*.csv"))
    if not csvs:
        raise FileNotFoundError(f"No fvalue CSV files found in {DATA_DIR}")
    return csvs[-1]


def _load_from_csv() -> tuple[pd.DataFrame, str]:
    path = _latest_fvalue_csv()
    df = pd.read_csv(
        path,
        encoding="utf-8-sig",
        header=0,
        usecols=range(13),
        dtype=str,
    )
    df.columns = FVALUE_RAW_COLS
    df = _clean_df(df)
    return df, f"CSV — {path.name}"


# ---------------------------------------------------------------------------
# Parsing and cleaning
# ---------------------------------------------------------------------------

def _parse_fvalue(s: str | float) -> dict:
    """
    Explode a pipe-delimited f_value string into named fields.
    Handles variable segment counts and app names containing '|'.
    """
    result = {
        "campaign_id": None,
        "format": None,
        "app_id": None,
        "app_name": None,
        "creative_type": None,
    }
    if pd.isna(s) or not str(s).strip():
        return result

    parts = str(s).split("|")
    # Strip trailing empty segments (strings end with |)
    while parts and parts[-1] == "":
        parts.pop()

    n = len(parts)
    if n < 3:
        return result  # only "bm|moloco" — no campaign info

    # Position 2 is sometimes a short tag like "BF" (Black Friday) instead of campaign_id
    base = 2
    if n >= 4 and len(parts[2]) <= 3 and parts[2].isalpha():
        base = 3  # skip the tag

    result["campaign_id"] = parts[base] if n > base else None
    result["format"] = parts[base + 1] if n > base + 1 else None
    result["app_id"] = parts[base + 2] if n > base + 2 else None

    # Remaining segments after app_id form app_name and optionally creative_type
    remaining = parts[base + 3:] if n > base + 3 else []
    if remaining:
        if remaining[-1].lower() in _CREATIVE_TYPES:
            result["creative_type"] = remaining[-1].lower()
            result["app_name"] = "|".join(remaining[:-1]) if len(remaining) > 1 else None
        else:
            result["app_name"] = "|".join(remaining)

    return result


def _clean_df(df: pd.DataFrame) -> pd.DataFrame:
    # Drop rows with no date
    df = df[df["date"].notna() & ~df["date"].str.strip().isin(["", "Total"])]
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df[df["date"].notna()]

    # Numeric columns
    for col in ["nb_users", "nb_orders", "nb_gmv", "ab_users", "ab_orders", "ab_gmv"]:
        df[col] = pd.to_numeric(
            df[col].str.replace(r"[$,]", "", regex=True).replace({"#VALUE!": np.nan, "#DIV/0!": np.nan, "": np.nan}),
            errors="coerce",
        )

    # Drop rows with no AB GMV data
    df = df[df["ab_gmv"].notna()]

    # Explode f_value
    parsed = df["f_value"].apply(_parse_fvalue)
    parsed_df = pd.DataFrame(list(parsed), index=df.index)
    df = pd.concat([df, parsed_df], axis=1)

    # Clean string dimensions
    for col in ["country", "os_type", "channel", "format", "creative_type"]:
        df[col] = df[col].fillna("").str.strip().replace("", None)

    return df.sort_values("date").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Future loader stub
# ---------------------------------------------------------------------------

def _load_from_feishu_public() -> tuple[pd.DataFrame, str]:
    from feishu_reader import read_sheet
    import numpy as np
    rows = read_sheet("F值报告")
    df = _rows_feishu_to_df(rows)
    return df, "Feishu (public share)"


def _rows_feishu_to_df(rows: list[list]) -> pd.DataFrame:
    import numpy as np
    # Row 0 = headers (skip); rows 1+ = data
    data = rows[1:]
    df = pd.DataFrame(data, columns=FVALUE_RAW_COLS)
    # Convert Excel serial date
    df["date"] = df["date"].apply(
        lambda v: _excel_date(v) if isinstance(v, (int, float)) else pd.to_datetime(v, errors="coerce")
    )
    df = df[df["date"].notna()]
    # Numeric columns — formula errors become NaN
    for col in ["nb_users", "nb_orders", "nb_gmv", "ab_users", "ab_orders", "ab_gmv"]:
        df[col] = df[col].apply(lambda v: None if isinstance(v, str) else v)
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df[df["ab_gmv"].notna()]
    # String dimensions
    for col in ["country", "os_type", "channel", "format", "f_value"]:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip().replace("", None)
    # Explode f_value
    parsed = df["f_value"].apply(_parse_fvalue)
    parsed_df = pd.DataFrame(list(parsed), index=df.index)
    df = pd.concat([df, parsed_df], axis=1)
    for col in ["format", "creative_type"]:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip().replace("", None)
    return df.sort_values("date").reset_index(drop=True)


def _excel_date(v):
    import numpy as np
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
