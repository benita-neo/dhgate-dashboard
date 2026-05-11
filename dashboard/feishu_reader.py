"""
Playwright-based reader for DHGate public Feishu wiki-embedded sheet.

Feishu loads sheet data lazily by tab — navigating to the sheet-specific URL
is required; programmatic tab-switching does not trigger data loading.

Returns raw rows as list[list]:
  - Row 0: header strings (first cell may be None for the unlabelled "Date" column)
  - Row 1+: data (dates as Excel serial ints/floats, numbers as floats,
             formula errors like "#DIV/0!" as strings, empty cells as None)

Usage:
    from feishu_reader import read_sheet
    rows = read_sheet("日报")            # 日报 tab
    rows = read_sheet("F值报告")         # F值报告 tab
    rows = read_sheet("Campaign By day") # Campaign By day tab
"""

from playwright.sync_api import sync_playwright

_WIKI_BASE = "https://sjfx.feishu.cn/wiki/XcEnw6FqtivVmakanQjcqABNnHb?sheet="

_SHEET_IDS: dict[str, str] = {
    "日报":            "9opTBc",
    "F值报告":         "xbwoRM",
    "Campaign By day": "eNkN6W",
}

# Number of data columns to read per tab (trailing empty cols are skipped)
_SHEET_NCOLS: dict[str, int] = {
    "日报":            16,
    "F值报告":         13,   # col 13 is a formula-derived campaign ID; parsed from f_value instead
    "Campaign By day": 16,
}

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def read_sheet(sheet_name: str) -> list[list]:
    """
    Read all data rows from the named Feishu sheet tab.
    Returns rows as list[list] (row 0 = headers, row 1+ = data).
    Raises KeyError if sheet_name is not one of the known tabs.
    """
    sheet_id = _SHEET_IDS[sheet_name]
    n_cols = _SHEET_NCOLS[sheet_name]
    url = _WIKI_BASE + sheet_id

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        ctx = browser.new_context(
            user_agent=_USER_AGENT,
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_function(
                "typeof window.spread !== 'undefined' "
                "&& window.spread !== null "
                "&& typeof window.spread.getActiveSheet === 'function'",
                timeout=45_000,
            )
            page.wait_for_timeout(4_000)
            return page.evaluate(_reader_js(n_cols))
        finally:
            browser.close()


def _reader_js(n_cols: int) -> str:
    return f"""
    () => {{
        const sheet = window.spread.getActiveSheet();
        let maxRow;
        try {{
            maxRow = sheet.getLastBlankRowPos();
            if (!maxRow || maxRow <= 0) maxRow = sheet.getRowCount();
        }} catch(e) {{
            maxRow = sheet.getRowCount();
        }}

        const nCols = {n_cols};
        const result = [];
        let consecutiveEmpty = 0;

        for (let r = 0; r < maxRow; r++) {{
            const row = [];
            let hasData = false;
            for (let c = 0; c < nCols; c++) {{
                const v = sheet.getValue(r, c);
                row.push(v);
                if (v !== null && v !== undefined) hasData = true;
            }}
            if (hasData) {{
                result.push(row);
                consecutiveEmpty = 0;
            }} else {{
                consecutiveEmpty++;
                if (consecutiveEmpty >= 5 && result.length > 0) break;
            }}
        }}
        return result;
    }}
    """
