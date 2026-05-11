import sys
from pathlib import Path
from datetime import timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).parent.parent))
from campaign_by_day_loader import DISPLAY_NAMES, load_campaign_data

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="DHGate — Campaign By Day",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def fmt_usd(v, decimals=0):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"${v:,.{decimals}f}"


def fmt_num(v, decimals=0):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v:,.{decimals}f}"


def fmt_pct(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v:.2f}%"


# ---------------------------------------------------------------------------
# Data loading (cached)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600)
def get_data():
    return load_campaign_data()


df, source_label = get_data()

# Build campaign label map: "campaign_name (id)" for display
campaign_label_map = {}  # label → campaign_id
for _, row in df[["campaign_id", "campaign_name"]].dropna().drop_duplicates("campaign_id").iterrows():
    label = f"{row['campaign_name']}  [{row['campaign_id']}]"
    campaign_label_map[label] = row["campaign_id"]

# ---------------------------------------------------------------------------
# Sidebar — filters
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("Campaign By Day")
    st.caption(f"Source: {source_label}")
    st.divider()

    min_date = df["date"].min().date()
    max_date = df["date"].max().date()
    default_start = max(min_date, max_date - timedelta(days=29))

    date_range = st.date_input(
        "Date range",
        value=(default_start, max_date),
        min_value=min_date,
        max_value=max_date,
    )

    if len(date_range) != 2:
        st.info("Select a start and end date.")
        st.stop()

    start_date, end_date = date_range

    st.divider()

    # Campaign filter (shows full name + ID)
    all_labels = sorted(campaign_label_map.keys())
    selected_labels = st.multiselect("Campaign", all_labels, default=[])
    selected_campaign_ids = [campaign_label_map[l] for l in selected_labels]

    # Product filter
    product_options = sorted(df["product"].dropna().unique())
    selected_products = st.multiselect("Product", product_options, default=product_options)

    # OS filter
    os_options = sorted(df["os_type"].dropna().unique())
    selected_os = st.multiselect("OS", os_options, default=os_options)

    st.divider()
    st.caption(
        f"Full dataset: {min_date.strftime('%d %b %Y')} → {max_date.strftime('%d %b %Y')}"
    )
    st.caption(f"Total campaigns: {df['campaign_id'].nunique()}")

# ---------------------------------------------------------------------------
# Filter
# ---------------------------------------------------------------------------

mask = (
    (df["date"].dt.date >= start_date)
    & (df["date"].dt.date <= end_date)
)
if selected_campaign_ids:
    mask &= df["campaign_id"].isin(selected_campaign_ids)
if selected_products:
    mask &= df["product"].isin(selected_products)
if selected_os:
    mask &= df["os_type"].isin(selected_os)

fdf = df[mask].copy()

if fdf.empty:
    st.warning("No data for the selected filters.")
    st.stop()

n_days = (end_date - start_date).days + 1

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

h1, h2 = st.columns([3, 1])
with h1:
    st.title("📈 DHGate Campaign By Day")
with h2:
    st.markdown(f"**Last data point:** {max_date.strftime('%d %b %Y')}")
    st.markdown(
        f"**Period:** {start_date.strftime('%d %b')} – {end_date.strftime('%d %b %Y')} "
        f"({n_days}d)"
    )

st.divider()

# ---------------------------------------------------------------------------
# KPI cards
# ---------------------------------------------------------------------------

total_spend = fdf["spend"].sum()
total_gmv = fdf["backend_gmv"].sum()
total_orders = fdf["backend_orders"].sum()
b_roi = total_gmv / total_spend if total_spend else np.nan
n_active = fdf["campaign_id"].nunique()

k1, k2, k3, k4, k5 = st.columns(5)
with k1:
    st.metric("Total Spend", fmt_usd(total_spend), help="Ad spend in selected period.")
with k2:
    st.metric("Backend GMV", fmt_usd(total_gmv), help="Backend GMV reported by client.")
with k3:
    st.metric("Backend ROI", fmt_num(b_roi, decimals=2), help="Backend GMV / Spend (weighted).")
with k4:
    st.metric("Backend Orders", fmt_num(total_orders), help="Backend orders.")
with k5:
    st.metric("Active Campaigns", fmt_num(n_active), help="Distinct campaigns in period.")

st.divider()

# ---------------------------------------------------------------------------
# Top 30 spending campaigns — fixed last 30 days window
# ---------------------------------------------------------------------------

st.subheader("🏆 Top 30 Spending Campaigns in the Last 30 Days")

_last30_end = df["date"].max().date()
_last30_start = _last30_end - timedelta(days=29)
st.caption(f"Fixed window: {_last30_start.strftime('%d %b %Y')} → {_last30_end.strftime('%d %b %Y')} · Independent of sidebar filters.")

_last30_df = df[
    (df["date"].dt.date >= _last30_start)
    & (df["date"].dt.date <= _last30_end)
]

def _top30_table(os_label: str) -> pd.DataFrame:
    t = (
        _last30_df[_last30_df["os_type"].str.upper() == os_label.upper()]
        .groupby(["campaign_id", "campaign_name"])
        .agg(spend=("spend", "sum"))
        .reset_index()
        .sort_values("spend", ascending=False)
        .head(30)
        .reset_index(drop=True)
    )
    t.index = t.index + 1
    out = t[["campaign_name", "campaign_id", "spend"]].copy()
    out.columns = ["Campaign Name", "Campaign ID", "Spend (USD)"]
    out["Spend (USD)"] = out["Spend (USD)"].round(2)
    return out

_col_config = {"Spend (USD)": st.column_config.NumberColumn(format="$%.2f")}

t1, t2 = st.columns(2)
with t1:
    st.markdown("**iOS**")
    st.dataframe(_top30_table("IOS"), use_container_width=True, column_config=_col_config)
with t2:
    st.markdown("**Android**")
    st.dataframe(_top30_table("ANDROID"), use_container_width=True, column_config=_col_config)

st.divider()

# ---------------------------------------------------------------------------
# Charts — row 1: Spend over time | Backend ROI over time
# ---------------------------------------------------------------------------

daily = fdf.groupby("date").agg(
    spend=("spend", "sum"),
    backend_gmv=("backend_gmv", "sum"),
    backend_orders=("backend_orders", "sum"),
).reset_index()
daily["backend_roi"] = np.where(daily["spend"] > 0, daily["backend_gmv"] / daily["spend"], np.nan)

fig_spend = go.Figure()
fig_spend.add_trace(go.Bar(
    x=daily["date"], y=daily["spend"],
    name="Daily Spend", marker_color="#4F8EF7", opacity=0.75,
))
fig_spend.update_layout(
    title="Daily Spend (all selected campaigns)",
    hovermode="x unified",
    height=300, margin=dict(t=60, b=20, l=10, r=10),
    yaxis=dict(tickprefix="$"),
    xaxis_title="",
)

fig_roi = go.Figure()
fig_roi.add_trace(go.Scatter(
    x=daily["date"], y=daily["backend_roi"],
    name="Backend ROI", line=dict(color="#4FCF77", width=2.5),
    mode="lines+markers", marker=dict(size=4), connectgaps=False,
))
fig_roi.update_layout(
    title="Backend ROI (weighted daily)",
    hovermode="x unified",
    height=300, margin=dict(t=60, b=20, l=10, r=10),
    xaxis_title="",
)

c1, c2 = st.columns(2)
c1.plotly_chart(fig_spend, use_container_width=True)
c2.plotly_chart(fig_roi, use_container_width=True)

# ---------------------------------------------------------------------------
# Charts — row 2: Campaign spend trend (top 8) | GMV by product (horizontal)
# ---------------------------------------------------------------------------

colors = ["#4F8EF7", "#F7A84F", "#4FCF77", "#F7584F", "#9B7EF7",
          "#E377C2", "#8C564B", "#17BECF"]

if selected_campaign_ids:
    trend_ids = selected_campaign_ids[:8]
else:
    trend_ids = (
        fdf.groupby("campaign_id")["spend"].sum().nlargest(8).index.tolist()
    )

camp_daily = (
    fdf[fdf["campaign_id"].isin(trend_ids)]
    .groupby(["date", "campaign_id", "campaign_name"])["spend"]
    .sum()
    .reset_index()
)

def _short_label(name: str, cid: str) -> str:
    if not pd.notna(name):
        return cid
    # Keep: product_MARKET_TYPE — drop _IAP_..._date suffix
    s = name.replace("dhgate_", "")
    s = s.split("_IAP")[0].split("_Kelsey")[0].split("_Iris")[0]
    return s

fig_camp = go.Figure()
for i, cid in enumerate(trend_ids):
    cdata = camp_daily[camp_daily["campaign_id"] == cid]
    cname = cdata["campaign_name"].iloc[0] if not cdata.empty else cid
    short = _short_label(cname, cid)
    fig_camp.add_trace(go.Scatter(
        x=cdata["date"], y=cdata["spend"],
        name=short,
        line=dict(color=colors[i % len(colors)], width=2),
        mode="lines", connectgaps=False,
        hovertemplate=f"<b>{short}</b><br>%{{x}}<br>Spend: $%{{y:,.0f}}<extra></extra>",
    ))
fig_camp.update_layout(
    title="Campaign Spend Trend" + (" (selected)" if selected_campaign_ids else " (top 8 by spend)"),
    hovermode="x unified",
    legend=dict(
        orientation="v", yanchor="top", y=1, xanchor="left", x=1.02,
        font=dict(size=10), bgcolor="rgba(0,0,0,0)",
    ),
    height=380, margin=dict(t=50, b=20, l=10, r=180),
    yaxis=dict(tickprefix="$"),
    xaxis_title="",
)

# Product chart — horizontal bars so names are readable
by_product = (
    fdf.groupby("product")
    .agg(backend_gmv=("backend_gmv", "sum"), spend=("spend", "sum"))
    .reset_index()
    .sort_values("backend_gmv", ascending=True)  # ascending for horizontal (top = highest)
    .tail(20)
)
by_product["backend_roi"] = np.where(
    by_product["spend"] > 0, by_product["backend_gmv"] / by_product["spend"], np.nan
)

fig_product = go.Figure()
fig_product.add_trace(go.Bar(
    y=by_product["product"], x=by_product["backend_gmv"],
    name="Backend GMV", marker_color="#9B7EF7", opacity=0.8,
    orientation="h",
    hovertemplate="<b>%{y}</b><br>GMV: $%{x:,.0f}<extra></extra>",
))
fig_product.add_trace(go.Scatter(
    y=by_product["product"], x=by_product["backend_roi"],
    name="Backend ROI", marker=dict(color="#F7A84F", size=8, symbol="diamond"),
    mode="markers", xaxis="x2",
    hovertemplate="<b>%{y}</b><br>ROI: %{x:.2f}<extra></extra>",
))
fig_product.update_layout(
    title="Backend GMV & ROI by Product (top 20)",
    hovermode="y unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    height=380, margin=dict(t=50, b=30, l=10, r=10),
    xaxis=dict(title="GMV (USD)", tickprefix="$"),
    xaxis2=dict(title="ROI", overlaying="x", side="top", showgrid=False),
    yaxis=dict(showgrid=False),
)

c3, c4 = st.columns(2)
c3.plotly_chart(fig_camp, use_container_width=True)
c4.plotly_chart(fig_product, use_container_width=True)

# ---------------------------------------------------------------------------
# Charts — row 3: Backend GMV & ROI by Campaign (top 20, horizontal)
# ---------------------------------------------------------------------------

by_campaign = (
    fdf.groupby(["campaign_id", "campaign_name"])
    .agg(backend_gmv=("backend_gmv", "sum"), spend=("spend", "sum"))
    .reset_index()
    .sort_values("backend_gmv", ascending=True)
    .tail(20)
)
by_campaign["backend_roi"] = np.where(
    by_campaign["spend"] > 0, by_campaign["backend_gmv"] / by_campaign["spend"], np.nan
)
by_campaign["label"] = by_campaign["campaign_name"].apply(
    lambda n: _short_label(n, "") if pd.notna(n) else ""
)

fig_camp_gmv = go.Figure()
fig_camp_gmv.add_trace(go.Bar(
    y=by_campaign["label"], x=by_campaign["backend_gmv"],
    name="Backend GMV", marker_color="#4F8EF7", opacity=0.8,
    orientation="h",
    hovertemplate="<b>%{y}</b><br>GMV: $%{x:,.0f}<extra></extra>",
))
fig_camp_gmv.add_trace(go.Scatter(
    y=by_campaign["label"], x=by_campaign["backend_roi"],
    name="Backend ROI", marker=dict(color="#F7584F", size=8, symbol="diamond"),
    mode="markers", xaxis="x2",
    hovertemplate="<b>%{y}</b><br>ROI: %{x:.2f}<extra></extra>",
))
fig_camp_gmv.update_layout(
    title="Backend GMV & ROI by Campaign (top 20 by GMV)",
    hovermode="y unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    height=520, margin=dict(t=50, b=30, l=10, r=10),
    xaxis=dict(title="GMV (USD)", tickprefix="$"),
    xaxis2=dict(title="ROI", overlaying="x", side="top", showgrid=False),
    yaxis=dict(showgrid=False),
)

st.plotly_chart(fig_camp_gmv, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Campaign summary table
# ---------------------------------------------------------------------------

st.subheader("📋 Campaign Summary")

camp_summary = (
    fdf.groupby(["campaign_id", "campaign_name", "product", "os_type"])
    .agg(
        spend=("spend", "sum"),
        impressions=("impressions", "sum"),
        clicks=("clicks", "sum"),
        backend_orders=("backend_orders", "sum"),
        backend_gmv=("backend_gmv", "sum"),
        days_active=("date", "nunique"),
    )
    .reset_index()
    .sort_values("spend", ascending=False)
)
camp_summary["backend_roi"] = np.where(
    camp_summary["spend"] > 0,
    camp_summary["backend_gmv"] / camp_summary["spend"],
    np.nan,
)
camp_summary["ctr"] = np.where(
    camp_summary["impressions"] > 0,
    camp_summary["clicks"] / camp_summary["impressions"] * 100,
    np.nan,
)

display_cols = {
    "campaign_name": "Campaign Name",
    "campaign_id": "Campaign ID",
    "product": "Product",
    "os_type": "OS",
    "spend": "Spend (USD)",
    "backend_gmv": "Backend GMV (USD)",
    "backend_roi": "Backend ROI",
    "backend_orders": "Backend Orders",
    "impressions": "Impressions",
    "ctr": "CTR (%)",
    "days_active": "Days Active",
}

disp = camp_summary[list(display_cols.keys())].copy()
disp.columns = list(display_cols.values())
disp["Spend (USD)"] = disp["Spend (USD)"].round(2)
disp["Backend GMV (USD)"] = disp["Backend GMV (USD)"].round(2)
disp["Backend ROI"] = disp["Backend ROI"].round(2)
disp["CTR (%)"] = disp["CTR (%)"].round(2)

st.dataframe(
    disp,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Spend (USD)": st.column_config.NumberColumn(format="$%.2f"),
        "Backend GMV (USD)": st.column_config.NumberColumn(format="$%.2f"),
        "Backend ROI": st.column_config.NumberColumn(format="%.2f"),
        "CTR (%)": st.column_config.NumberColumn(format="%.2f%%"),
    },
)
