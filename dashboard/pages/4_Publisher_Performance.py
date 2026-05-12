import sys
from pathlib import Path
from datetime import timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from fvalue_loader import load_fvalue_data

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="DHGate — Publisher Performance",
    page_icon="📱",
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
# Data loading
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600)
def get_data():
    return load_fvalue_data()


df_all, source_label = get_data()

# Rows with publisher info
df_pub = df_all[df_all["app_id"].notna()].copy()

# Stats for the data-availability callout
PUBLISHER_START = pd.Timestamp("2026-04-05")
df_apr_plus = df_all[df_all["date"] >= PUBLISHER_START]
n_no_pub = df_apr_plus["app_id"].isna().sum()
gmv_no_pub = df_apr_plus.loc[df_apr_plus["app_id"].isna(), "ab_gmv"].sum()
gmv_total  = df_apr_plus["ab_gmv"].sum()
pct_excluded = gmv_no_pub / gmv_total * 100 if gmv_total > 0 else 0

# ---------------------------------------------------------------------------
# Sidebar — filters
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("DHGate Publisher")
    st.caption(f"Source: {source_label}")
    st.divider()

    min_date = df_pub["date"].min().date()
    max_date = df_pub["date"].max().date()
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

    os_options = sorted(df_pub["os_type"].dropna().unique())
    selected_os = st.multiselect("OS", os_options, default=os_options)

    country_options = sorted(df_pub["country"].dropna().unique())
    selected_countries = st.multiselect("Country", country_options, default=country_options)

    format_options = sorted(df_pub["format"].dropna().unique())
    selected_formats = st.multiselect("Format", format_options, default=format_options)

    st.divider()
    st.caption(
        f"Publisher data available from **5 Apr 2026**.\n\n"
        f"{n_no_pub:,} rows (~{pct_excluded:.1f}% of GMV) from {df_apr_plus['app_id'].isna().sum()} "
        f"records have no publisher info and are excluded from this page."
    )

# ---------------------------------------------------------------------------
# Filter
# ---------------------------------------------------------------------------

mask = (
    (df_pub["date"].dt.date >= start_date)
    & (df_pub["date"].dt.date <= end_date)
)
if selected_os:
    mask &= df_pub["os_type"].isin(selected_os)
if selected_countries:
    mask &= df_pub["country"].isin(selected_countries)
if selected_formats:
    mask &= df_pub["format"].isin(selected_formats)

fdf = df_pub[mask].copy()

if fdf.empty:
    st.warning("No data for the selected filters.")
    st.stop()

n_days = (end_date - start_date).days + 1

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

h1, h2 = st.columns([3, 1])
with h1:
    st.title("📱 DHGate Publisher Performance")
with h2:
    st.markdown(f"**Last data point:** {max_date.strftime('%d %b %Y')}")
    st.markdown(
        f"**Period:** {start_date.strftime('%d %b')} – {end_date.strftime('%d %b %Y')} "
        f"({n_days}d)"
    )

st.info(
    f"📅 Publisher data is available from **5 Apr 2026** onwards. "
    f"An additional {n_no_pub:,} rows ({pct_excluded:.1f}% of AB GMV since Apr 5) have no publisher "
    f"info in the source data and are excluded from this page — they are included in all other pages.",
    icon=None,
)

st.divider()

# ---------------------------------------------------------------------------
# KPI cards
# ---------------------------------------------------------------------------

total_ab_gmv   = fdf["ab_gmv"].sum()
total_ab_orders = fdf["ab_orders"].sum()
total_nb_gmv   = fdf["nb_gmv"].sum()
total_nb_orders = fdf["nb_orders"].sum()
n_publishers   = fdf["app_name"].nunique()

k1, k2, k3, k4, k5 = st.columns(5)
with k1:
    st.metric("AB GMV", fmt_usd(total_ab_gmv), help="All-Buyer GMV in selected period.")
with k2:
    st.metric("AB Orders", fmt_num(total_ab_orders))
with k3:
    st.metric("NB GMV", fmt_usd(total_nb_gmv), help="New-Buyer GMV.")
with k4:
    st.metric("NB Orders", fmt_num(total_nb_orders))
with k5:
    st.metric("Active Publishers", fmt_num(n_publishers), help="Distinct app names with data in this period.")

st.divider()

# ---------------------------------------------------------------------------
# Charts — row 1: Publisher trend | Publisher bar
# ---------------------------------------------------------------------------

colors = ["#4F8EF7", "#F7A84F", "#4FCF77", "#F7584F", "#9B7EF7",
          "#E377C2", "#8C564B", "#17BECF", "#BCBD22", "#7F7F7F"]

top5_publishers = (
    fdf.groupby("app_name")["ab_gmv"]
    .sum()
    .nlargest(5)
    .index.tolist()
)

pub_daily = (
    fdf[fdf["app_name"].isin(top5_publishers)]
    .groupby(["date", "app_name"])["ab_gmv"]
    .sum()
    .reset_index()
)

fig_trend = go.Figure()
for i, pub in enumerate(top5_publishers):
    pdata = pub_daily[pub_daily["app_name"] == pub]
    fig_trend.add_trace(go.Scatter(
        x=pdata["date"], y=pdata["ab_gmv"],
        name=pub,
        line=dict(color=colors[i % len(colors)], width=2),
        mode="lines", connectgaps=False,
    ))
fig_trend.update_layout(
    title="Top 5 Publishers — Daily AB GMV",
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    height=360, margin=dict(t=80, b=20, l=10, r=10),
    yaxis=dict(tickprefix="$"), xaxis_title="",
)

by_pub = (
    fdf.groupby("app_name")
    .agg(ab_gmv=("ab_gmv", "sum"))
    .reset_index()
    .sort_values("ab_gmv", ascending=True)
    .tail(15)
)

fig_bar = go.Figure(go.Bar(
    x=by_pub["ab_gmv"],
    y=by_pub["app_name"],
    orientation="h",
    marker_color="#4F8EF7",
    text=by_pub["ab_gmv"].apply(lambda v: fmt_usd(v)),
    textposition="outside",
    hovertemplate="<b>%{y}</b><br>AB GMV: $%{x:,.0f}<extra></extra>",
))
fig_bar.update_layout(
    title="AB GMV by Publisher (top 15)",
    height=360,
    margin=dict(t=60, b=20, l=10, r=80),
    yaxis=dict(autorange="reversed"),
    xaxis=dict(tickprefix="$"), xaxis_title="",
)

c1, c2 = st.columns(2)
c1.plotly_chart(fig_trend, use_container_width=True)
c2.plotly_chart(fig_bar, use_container_width=True)

# ---------------------------------------------------------------------------
# Charts — row 2: NB GMV share by publisher | AB GMV by format
# ---------------------------------------------------------------------------

pub_nb = (
    fdf.groupby("app_name")
    .agg(ab_gmv=("ab_gmv", "sum"), nb_gmv=("nb_gmv", "sum"))
    .reset_index()
)
pub_nb["nb_share"] = np.where(
    pub_nb["ab_gmv"] > 0,
    pub_nb["nb_gmv"] / pub_nb["ab_gmv"] * 100,
    np.nan,
)
pub_nb = pub_nb.sort_values("ab_gmv", ascending=True).tail(15)

fig_nb = go.Figure(go.Bar(
    x=pub_nb["nb_share"],
    y=pub_nb["app_name"],
    orientation="h",
    marker_color="#4FCF77",
    text=pub_nb["nb_share"].apply(lambda v: f"{v:.1f}%" if not np.isnan(v) else ""),
    textposition="outside",
    hovertemplate="<b>%{y}</b><br>NB GMV Share: %{x:.1f}%<extra></extra>",
))
fig_nb.update_layout(
    title="NB GMV Share by Publisher (top 15 by AB GMV)",
    height=360,
    margin=dict(t=60, b=20, l=10, r=60),
    yaxis=dict(autorange="reversed"),
    xaxis=dict(ticksuffix="%"), xaxis_title="",
)

by_format = (
    fdf.groupby("format")
    .agg(ab_gmv=("ab_gmv", "sum"))
    .reset_index()
    .sort_values("ab_gmv", ascending=False)
)

fig_fmt = go.Figure(go.Bar(
    x=by_format["format"],
    y=by_format["ab_gmv"],
    marker_color="#F7A84F",
    text=by_format["ab_gmv"].apply(lambda v: fmt_usd(v)),
    textposition="outside",
    hovertemplate="<b>%{x}</b><br>AB GMV: $%{y:,.0f}<extra></extra>",
))
fig_fmt.update_layout(
    title="AB GMV by Format",
    height=360,
    margin=dict(t=60, b=20, l=10, r=10),
    yaxis=dict(tickprefix="$"), xaxis_title="",
)

c3, c4 = st.columns(2)
c3.plotly_chart(fig_nb, use_container_width=True)
c4.plotly_chart(fig_fmt, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Publisher breakdown table
# ---------------------------------------------------------------------------

st.subheader("🏆 Publisher Breakdown")

pub_table = (
    fdf.groupby("app_name")
    .agg(
        app_id=("app_id", "first"),
        ab_gmv=("ab_gmv", "sum"),
        ab_orders=("ab_orders", "sum"),
        nb_gmv=("nb_gmv", "sum"),
        nb_orders=("nb_orders", "sum"),
        formats=("format", lambda x: ", ".join(sorted(x.dropna().unique()))),
        n_campaigns=("campaign_id", "nunique"),
    )
    .reset_index()
    .sort_values("ab_gmv", ascending=False)
)
pub_table["nb_share"] = np.where(
    pub_table["ab_gmv"] > 0,
    pub_table["nb_gmv"] / pub_table["ab_gmv"] * 100,
    np.nan,
)

pub_table = pub_table.rename(columns={
    "app_name": "Publisher",
    "app_id": "App ID",
    "ab_gmv": "AB GMV (USD)",
    "ab_orders": "AB Orders",
    "nb_gmv": "NB GMV (USD)",
    "nb_orders": "NB Orders",
    "nb_share": "NB GMV Share (%)",
    "formats": "Formats",
    "n_campaigns": "Campaigns",
})
pub_table["AB GMV (USD)"] = pub_table["AB GMV (USD)"].round(2)
pub_table["NB GMV (USD)"] = pub_table["NB GMV (USD)"].round(2)
pub_table["NB GMV Share (%)"] = pub_table["NB GMV Share (%)"].round(1)

st.dataframe(
    pub_table,
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
    raw_cols = ["date", "country", "os_type", "app_id", "app_name", "format",
                "creative_type", "campaign_id", "nb_orders", "nb_gmv",
                "ab_orders", "ab_gmv"]
    raw_display = fdf[raw_cols].copy()
    raw_display["date"] = raw_display["date"].dt.strftime("%Y-%m-%d")
    st.dataframe(raw_display, use_container_width=True, hide_index=True)
