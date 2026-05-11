"""
Daily sync script: pull all three Feishu sheet tabs and save as CSV files.

Run manually:
    python sync_data.py

Or via GitHub Actions cron (see .github/workflows/sync_feishu.yml).

Saves files to ../data/ (same directory the loaders read from):
    dhgate_daily_manual_download_YYYY-MM-DD.csv
    dhgate_fvalue_manual_download_YYYY-MM-DD.csv
    dhgate_campaignbyday_manual_download_YYYY-MM-DD.csv
"""

import sys
import logging
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from feishu_reader import read_sheet
from loader import COLUMNS as DAILY_COLUMNS, _rows_feishu_to_df as _daily_to_df
from fvalue_loader import FVALUE_RAW_COLS, _rows_feishu_to_df as _fvalue_to_df
from campaign_by_day_loader import COLUMNS as CAMP_COLUMNS, _rows_feishu_to_df as _camp_to_df

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
TODAY = date.today().isoformat()


def sync_tab(tab_name: str, to_df_fn, filename_prefix: str) -> Path:
    log.info(f"Fetching {tab_name!r} from Feishu...")
    rows = read_sheet(tab_name)
    log.info(f"  → {len(rows)} rows received")

    df = to_df_fn(rows)
    log.info(f"  → {len(df)} clean data rows")

    out_path = DATA_DIR / f"{filename_prefix}_{TODAY}.csv"
    df.to_csv(out_path, index=False)
    log.info(f"  → saved to {out_path}")
    return out_path


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    sync_tab("日报",          _daily_to_df,  "dhgate_daily_manual_download")
    sync_tab("F值报告",        _fvalue_to_df, "dhgate_fvalue_manual_download")
    sync_tab("Campaign By day", _camp_to_df,  "dhgate_campaignbyday_manual_download")

    log.info("Sync complete.")


if __name__ == "__main__":
    main()
