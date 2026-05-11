import sys
from pathlib import Path
from datetime import timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from fvalue_loader import DISPLAY_NAMES, load_fvalue_data
from campaign_by_day_loader import get_campaign_name_map

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="DHGate — F值报告",
    page_icon="🎨",
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


# ---------------------------------------------------------------------------
# Data loading (cached)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600)
def get_data():
    return load_fvalue_data()


df, source_label = get_data()

# Campaign name lookup (from Campaign By day sheet) — falls back gracefully if unavailable
try:
    _name_map = get_campaign_name_map()
except Exception:
    _name_map = {}

def _campaign_label(cid: str) -> str:
    name = _name_map.get(cid)
    return f"{name}  [{cid}]" if name else cid

# ---------------------------------------------------------------------------
# Sidebar — filters
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("DHGate F值报告")
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

    # Campaign filter — labels show full name + ID where available
    campaign_options = sorted(df["campaign_id"].dropna().unique())
    campaign_labels = [_campaign_label(c) for c in campaign_options]
    label_to_id = dict(zip(campaign_labels, campaign_options))
    selected_labels = st.multiselect("Campaign", campaign_labels, default=[])
    selected_campaigns = [label_to_id[l] for l in selected_labels]

    # OS filter
    os_options = sorted(df["os_type"].dropna().unique())
    selected_os = st.multiselect("OS", os_options, default=os_options)

    # Country filter
    country_options = sorted(df["country"].dropna().unique())
    selected_countries = st.multiselect("Country", country_options, default=country_options)

    # Format filter
    format_options = sorted(df["format"].dropna().unique())
    selected_formats = st.multiselect("Format", format_options, default=format_options)

    st.divider()
    st.caption(
        f"Full dataset: {min_date.strftime('%d %b %Y')} → {max_date.strftime('%d %b %Y')}"
    )
    st.caption(
        "**NB** = New Buyer · **AB** = All Buyers\n\n"
        "f_value fields are exploded from the pipe-delimited creative identifier string."
    )

# ---------------------------------------------------------------------------
# Filter
# ---------------------------------------------------------------------------

mask = (
    (df["date"].dt.date >= start_date)
    & (df["date"].dt.date <= end_date)
)
if selected_campaigns:
    mask &= df["campaign_id"].isin(selected_campaigns)
if selected_os:
    mask &= df["os_type"].isin(selected_os)
if selected_countries:
    mask &= df["country"].isin(selected_countries)
if selected_formats:
    mask &= df["format"].isin(selected_formats)

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
    st.title("🎨 DHGate F值报告 — Creative Performance")
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

total_ab_gmv = fdf["ab_gmv"].sum()
total_ab_orders = fdf["ab_orders"].sum()
total_nb_gmv = fdf["nb_gmv"].sum()
total_nb_orders = fdf["nb_orders"].sum()
n_campaigns = fdf["campaign_id"].nunique()

k1, k2, k3, k4, k5 = st.columns(5)

with k1:
    st.metric("AB GMV", fmt_usd(total_ab_gmv), help="All-Buyer GMV in selected period.")
with k2:
    st.metric("AB Orders", fmt_num(total_ab_orders), help="All-Buyer orders.")
with k3:
    st.metric("NB GMV", fmt_usd(total_nb_gmv), help="New-Buyer GMV.")
with k4:
    st.metric("NB Orders", fmt_num(total_nb_orders), help="New-Buyer orders.")
with k5:
    st.metric(
        "Active Campaigns",
        fmt_num(n_campaigns),
        help="Distinct campaign IDs with data in this period.",
    )

st.divider()

# ---------------------------------------------------------------------------
# Charts — row 1: AB GMV over time | NB share over time
# ---------------------------------------------------------------------------

daily = fdf.groupby("date").agg(
    ab_gmv=("ab_gmv", "sum"),
    nb_gmv=("nb_gmv", "sum"),
    ab_orders=("ab_orders", "sum"),
).reset_index()
daily["nb_share_pct"] = np.where(
    daily["ab_gmv"] > 0, daily["nb_gmv"] / daily["ab_gmv"] * 100, np.nan
)

fig_gmv = go.Figure()
fig_gmv.add_trace(go.Bar(
    x=daily["date"], y=daily["ab_gmv"],
    name="AB GMV", marker_color="#4F8EF7", opacity=0.8,
))
fig_gmv.add_trace(go.Bar(
    x=daily["date"], y=daily["nb_gmv"],
    name="NB GMV", marker_color="#F7A84F", opacity=0.8,
))
fig_gmv.update_layout(
    title="Daily GMV — All Buyers vs New Buyers",
    barmode="overlay",
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    height=340, margin=dict(t=60, b=20, l=10, r=10),
    yaxis=dict(tickprefix="$"),
    xaxis_title="",
)

fig_nb = go.Figure()
fig_nb.add_trace(go.Scatter(
    x=daily["date"], y=daily["nb_share_pct"],
    name="NB GMV share (%)", line=dict(color="#4FCF77", width=2.5),
    mode="lines+markers", marker=dict(size=4), connectgaps=False,
))
fig_nb.update_layout(
    title="New Buyer GMV Share (% of AB GMV)",
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    height=340, margin=dict(t=60, b=20, l=10, r=10),
    yaxis=dict(ticksuffix="%"),
    xaxis_title="",
)

c1, c2 = st.columns(2)
c1.plotly_chart(fig_gmv, use_container_width=True)
c2.plotly_chart(fig_nb, use_container_width=True)

# ---------------------------------------------------------------------------
# Charts — row 2: Campaign trend | AB GMV by country
# ---------------------------------------------------------------------------

# Campaign trend — top 5 by total AB GMV (or selected campaigns if filtered)
if selected_campaigns:
    trend_campaigns = selected_campaigns
else:
    top5 = (
        fdf.groupby("campaign_id")["ab_gmv"]
        .sum()
        .nlargest(5)
        .index.tolist()
    )
    trend_campaigns = top5

campaign_daily = (
    fdf[fdf["campaign_id"].isin(trend_campaigns)]
    .groupby(["date", "campaign_id"])["ab_gmv"]
    .sum()
    .reset_index()
)

colors = ["#4F8EF7", "#F7A84F", "#4FCF77", "#F7584F", "#9B7EF7",
          "#E377C2", "#8C564B", "#17BECF", "#BCBD22", "#7F7F7F"]

fig_trend = go.Figure()
for i, cid in enumerate(trend_campaigns):
    cdata = campaign_daily[campaign_daily["campaign_id"] == cid]
    fig_trend.add_trace(go.Scatter(
        x=cdata["date"], y=cdata["ab_gmv"],
        name=cid,
        line=dict(color=colors[i % len(colors)], width=2),
        mode="lines", connectgaps=False,
    ))
fig_trend.update_layout(
    title="Campaign AB GMV Trend" + (" (selected)" if selected_campaigns else " (top 5)"),
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    height=340, margin=dict(t=60, b=20, l=10, r=10),
    yaxis=dict(tickprefix="$"),
    xaxis_title="",
)

by_country = (
    fdf.groupby("country")
    .agg(ab_gmv=("ab_gmv", "sum"))
    .reset_index()
    .sort_values("ab_gmv", ascending=False)
    .head(15)
)

fig_country = go.Figure(go.Bar(
    x=by_country["ab_gmv"],
    y=by_country["country"],
    orientation="h",
    marker_color="#F7584F",
    text=by_country["ab_gmv"].apply(lambda v: fmt_usd(v)),
    textposition="outside",
    hovertemplate="<b>%{y}</b><br>AB GMV: $%{x:,.0f}<extra></extra>",
))
fig_country.update_layout(
    title="AB GMV by Country",
    height=340,
    margin=dict(t=60, b=20, l=10, r=80),
    yaxis=dict(autorange="reversed"),
    xaxis=dict(tickprefix="$"),
    xaxis_title="",
)

c3, c4 = st.columns(2)
c3.plotly_chart(fig_trend, use_container_width=True)
c4.plotly_chart(fig_country, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Creative breakdown table — format × creative_type
# ---------------------------------------------------------------------------

st.subheader("🎯 Creative Type Breakdown")

breakdown = (
    fdf.groupby(
        [c for c in ["format", "creative_type"] if fdf[c].notna().any()],
        dropna=False,
    )
    .agg(
        ab_gmv=("ab_gmv", "sum"),
        ab_orders=("ab_orders", "sum"),
        nb_gmv=("nb_gmv", "sum"),
        nb_orders=("nb_orders", "sum"),
        n_campaigns=("campaign_id", "nunique"),
    )
    .reset_index()
    .sort_values("ab_gmv", ascending=False)
)

breakdown["nb_share"] = np.where(
    breakdown["ab_gmv"] > 0,
    breakdown["nb_gmv"] / breakdown["ab_gmv"] * 100,
    np.nan,
)

display_cols = {
    "format": "Format",
    "creative_type": "Creative Type",
    "ab_gmv": "AB GMV (USD)",
    "ab_orders": "AB Orders",
    "nb_gmv": "NB GMV (USD)",
    "nb_orders": "NB Orders",
    "nb_share": "NB GMV Share (%)",
    "n_campaigns": "Campaigns",
}

disp = breakdown[[c for c in display_cols if c in breakdown.columns]].copy()
disp.columns = [display_cols[c] for c in disp.columns]
disp["AB GMV (USD)"] = disp["AB GMV (USD)"].round(2)
disp["NB GMV (USD)"] = disp["NB GMV (USD)"].round(2)
disp["NB GMV Share (%)"] = disp["NB GMV Share (%)"].round(1)

st.dataframe(
    disp,
    use_container_width=True,
    hide_index=True,
    column_config={
        "AB GMV (USD)": st.column_config.NumberColumn(format="$%.2f"),
        "NB GMV (USD)": st.column_config.NumberColumn(format="$%.2f"),
        "NB GMV Share (%)": st.column_config.NumberColumn(format="%.1f%%"),
    },
)

# ---------------------------------------------------------------------------
# Raw data expander
# ---------------------------------------------------------------------------

with st.expander("📋 Raw Data (filtered)", expanded=False):
    raw_cols = ["date", "country", "os_type", "campaign_id", "format",
                "creative_type", "nb_users", "nb_orders", "nb_gmv",
                "ab_users", "ab_orders", "ab_gmv"]
    raw_display = fdf[raw_cols].copy()
    raw_display["date"] = raw_display["date"].dt.strftime("%Y-%m-%d")
    raw_display.columns = [DISPLAY_NAMES.get(c, c) for c in raw_cols]
    st.dataframe(raw_display, use_container_width=True, hide_index=True)
