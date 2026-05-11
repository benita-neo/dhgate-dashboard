import sys
from pathlib import Path
from datetime import timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).parent))
from loader import DISPLAY_NAMES, load_daily_data

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="DHGate Performance Dashboard — 日报",
    page_icon="📊",
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


def fmt_num(v, decimals=2):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v:,.{decimals}f}"


def fmt_pct(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v:.2f}%"


def pct_change(current, prior):
    if prior is None or prior == 0 or (isinstance(prior, float) and np.isnan(prior)):
        return None
    return (current - prior) / abs(prior) * 100


def delta_str(pct):
    if pct is None:
        return None
    return f"{pct:+.1f}%"


def prior_coverage(series: pd.Series, n_days: int) -> float:
    """Fraction of prior-period days with valid (non-zero, non-null) values."""
    if n_days == 0:
        return 0.0
    valid = series.notna() & (series != 0)
    return valid.sum() / n_days


def guarded_delta(current, prior_series: pd.Series, n_days: int, threshold: float = 0.5):
    """Return delta % only if prior period has >=threshold coverage; else None."""
    if prior_coverage(prior_series, n_days) < threshold:
        return None
    pri = prior_series.sum()
    return pct_change(current, pri)


# ---------------------------------------------------------------------------
# Data loading (cached)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600)
def get_data():
    return load_daily_data()


df, source_label = get_data()

# ---------------------------------------------------------------------------
# Sidebar — filters
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("DHGate 日报")
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
    st.caption(
        f"Full dataset: {min_date.strftime('%d %b %Y')} → {max_date.strftime('%d %b %Y')}"
    )

# ---------------------------------------------------------------------------
# Filter — current and prior periods
# ---------------------------------------------------------------------------

fdf = df[
    (df["date"].dt.date >= start_date) & (df["date"].dt.date <= end_date)
].copy()

n_days = (end_date - start_date).days + 1
prior_end = start_date - timedelta(days=1)
prior_start = prior_end - timedelta(days=n_days - 1)
pdf = df[
    (df["date"].dt.date >= prior_start) & (df["date"].dt.date <= prior_end)
].copy()

if fdf.empty:
    st.warning("No data for the selected period.")
    st.stop()

# ---------------------------------------------------------------------------
# KPI calculations
# ---------------------------------------------------------------------------

cur_spend = fdf["spend"].sum()
pri_spend = pdf["spend"].sum()

# Weighted ROAS = total attributed revenue / total spend (more stable than mean of daily)
cur_d1_roas = (
    fdf["d1_purchase_value"].sum() / cur_spend if cur_spend else np.nan
)
pri_d1_roas = (
    pdf["d1_purchase_value"].sum() / pri_spend if pri_spend else np.nan
)

# Weighted backend ROI = total backend GMV / total spend
cur_b_roi = fdf["backend_gmv"].sum() / cur_spend if cur_spend else np.nan
pri_b_roi = pdf["backend_gmv"].sum() / pri_spend if pri_spend else np.nan

cur_b_gmv = fdf["backend_gmv"].sum()
pri_b_gmv = pdf["backend_gmv"].sum()

cur_b_orders = int(fdf["backend_orders"].sum())
pri_b_orders = pdf["backend_orders"].sum()

# Delta guards — suppress delta if prior period has <50% valid days for that metric
_n_prior = len(pdf)
_delta_spend = guarded_delta(cur_spend, pdf["spend"], _n_prior)
_delta_d1_roas = guarded_delta(
    cur_d1_roas,
    pdf["d1_purchase_value"] / pdf["spend"].replace(0, np.nan),
    _n_prior,
)
_delta_b_roi = guarded_delta(
    cur_b_roi,
    pdf["backend_gmv"] / pdf["spend"].replace(0, np.nan),
    _n_prior,
)
_delta_b_gmv = guarded_delta(cur_b_gmv, pdf["backend_gmv"], _n_prior)
_delta_b_orders = guarded_delta(cur_b_orders, pdf["backend_orders"], _n_prior)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

h1, h2 = st.columns([3, 1])
with h1:
    st.title("📊 DHGate Performance Dashboard — 日报")
with h2:
    st.markdown(f"**Last data point:** {max_date.strftime('%d %b %Y')}")
    st.markdown(
        f"**Period:** {start_date.strftime('%d %b')} – {end_date.strftime('%d %b %Y')} "
        f"({n_days}d) vs prior {n_days}d"
    )

st.divider()

# ---------------------------------------------------------------------------
# KPI cards
# ---------------------------------------------------------------------------

k1, k2, k3, k4, k5 = st.columns(5)

with k1:
    st.metric(
        "Total Spend",
        fmt_usd(cur_spend),
        delta=delta_str(_delta_spend),
        delta_color="off",
        help="Total ad spend in selected period. Delta vs prior same-length period.",
    )
with k2:
    st.metric(
        "D1 ROAS",
        fmt_num(cur_d1_roas),
        delta=delta_str(_delta_d1_roas),
        help="D1 Purchase Value / Spend (weighted). Higher = better Moloco attribution.",
    )
with k3:
    st.metric(
        "Backend ROI",
        fmt_num(cur_b_roi),
        delta=delta_str(_delta_b_roi),
        help="Backend GMV / Spend (weighted). Client's actual return on ad spend.",
    )
with k4:
    st.metric(
        "Backend GMV",
        fmt_usd(cur_b_gmv),
        delta=delta_str(_delta_b_gmv),
        help="Total backend GMV reported by client.",
    )
with k5:
    st.metric(
        "Backend Orders",
        f"{cur_b_orders:,}",
        delta=delta_str(_delta_b_orders),
        help="Total backend orders reported by client.",
    )

st.caption(
    "ℹ️ Deltas vs the prior same-length period. "
    "A delta is hidden (—) when fewer than half the days in the prior period have valid data for that metric, "
    "to avoid misleading percentage swings from near-zero baselines."
)

st.divider()

# ---------------------------------------------------------------------------
# Charts — row 1: Spend | ROAS vs Backend ROI
# ---------------------------------------------------------------------------

fdf = fdf.copy()
fdf["spend_7d"] = fdf["spend"].rolling(7, min_periods=1).mean()

fig_spend = go.Figure()
fig_spend.add_trace(go.Bar(
    x=fdf["date"], y=fdf["spend"],
    name="Daily Spend", marker_color="#4F8EF7", opacity=0.75,
))
fig_spend.add_trace(go.Scatter(
    x=fdf["date"], y=fdf["spend_7d"],
    name="7-day avg", line=dict(color="#1a5fc4", width=2.5), mode="lines",
))
fig_spend.update_layout(
    title="Daily Spend",
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    height=340, margin=dict(t=60, b=20, l=10, r=10),
    yaxis=dict(tickprefix="$"),
    xaxis_title="",
)

fig_roas = go.Figure()
fig_roas.add_trace(go.Scatter(
    x=fdf["date"], y=fdf["d1_roas"],
    name="D1 ROAS", line=dict(color="#F7A84F", width=2.5),
    mode="lines+markers", marker=dict(size=4), connectgaps=False,
))
fig_roas.add_trace(go.Scatter(
    x=fdf["date"], y=fdf["backend_roi"],
    name="Backend ROI", line=dict(color="#4FCF77", width=2.5),
    mode="lines+markers", marker=dict(size=4), connectgaps=False,
))
fig_roas.update_layout(
    title="D1 ROAS vs Backend ROI",
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    height=340, margin=dict(t=60, b=20, l=10, r=10),
    xaxis_title="",
)

c1, c2 = st.columns(2)
c1.plotly_chart(fig_spend, use_container_width=True)
c2.plotly_chart(fig_roas, use_container_width=True)

# ---------------------------------------------------------------------------
# Charts — row 2: Backend GMV + Orders | CTR & CPM
# ---------------------------------------------------------------------------

fig_gmv = make_subplots(specs=[[{"secondary_y": True}]])
fig_gmv.add_trace(
    go.Bar(
        x=fdf["date"], y=fdf["backend_gmv"],
        name="Backend GMV", marker_color="#9B7EF7", opacity=0.75,
    ),
    secondary_y=False,
)
fig_gmv.add_trace(
    go.Scatter(
        x=fdf["date"], y=fdf["backend_orders"],
        name="Backend Orders", line=dict(color="#E377C2", width=2.5),
        mode="lines+markers", marker=dict(size=4),
    ),
    secondary_y=True,
)
fig_gmv.update_layout(
    title="Backend GMV & Orders",
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    height=340, margin=dict(t=60, b=20, l=10, r=10),
)
fig_gmv.update_yaxes(title_text="GMV (USD)", tickprefix="$", secondary_y=False)
fig_gmv.update_yaxes(title_text="Orders", secondary_y=True, showgrid=False)

fig_eff = make_subplots(specs=[[{"secondary_y": True}]])
fig_eff.add_trace(
    go.Scatter(
        x=fdf["date"], y=fdf["ctr"],
        name="CTR (%)", line=dict(color="#4F8EF7", width=2.5), mode="lines",
    ),
    secondary_y=False,
)
fig_eff.add_trace(
    go.Scatter(
        x=fdf["date"], y=fdf["cpm"],
        name="CPM ($)", line=dict(color="#F7584F", width=2.5), mode="lines",
    ),
    secondary_y=True,
)
fig_eff.update_layout(
    title="CTR & CPM",
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    height=340, margin=dict(t=60, b=20, l=10, r=10),
)
fig_eff.update_yaxes(title_text="CTR (%)", ticksuffix="%", secondary_y=False)
fig_eff.update_yaxes(title_text="CPM ($)", tickprefix="$", secondary_y=True, showgrid=False)

c3, c4 = st.columns(2)
c3.plotly_chart(fig_gmv, use_container_width=True)
c4.plotly_chart(fig_eff, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Insights
# ---------------------------------------------------------------------------

st.subheader("💡 Insights")

insights: list[tuple[str, str]] = []

# 1. Spend WoW
if pri_spend > 0:
    chg = pct_change(cur_spend, pri_spend)
    if chg is not None:
        direction = "increased" if chg > 0 else "decreased"
        sev = "warning" if abs(chg) > 30 else "info"
        insights.append((
            sev,
            f"Spend **{direction} {abs(chg):.1f}%** vs prior {n_days}-day period "
            f"({fmt_usd(pri_spend)} → {fmt_usd(cur_spend)}).",
        ))

# 2. Backend ROI vs D1 ROAS gap
if not np.isnan(cur_b_roi) and not np.isnan(cur_d1_roas) and cur_d1_roas > 0:
    gap = (cur_b_roi - cur_d1_roas) / cur_d1_roas * 100
    if gap >= 0:
        insights.append((
            "success",
            f"Backend ROI (**{cur_b_roi:.2f}**) is **{gap:.0f}% higher** than D1 ROAS "
            f"(**{cur_d1_roas:.2f}**) — client sees stronger returns than Moloco attribution.",
        ))
    else:
        insights.append((
            "warning",
            f"Backend ROI (**{cur_b_roi:.2f}**) is **{abs(gap):.0f}% lower** than D1 ROAS "
            f"(**{cur_d1_roas:.2f}**) — this gap may need discussion with the client.",
        ))

# 3. Backend GMV WoW
if pri_b_gmv > 0:
    chg = pct_change(cur_b_gmv, pri_b_gmv)
    if chg is not None:
        direction = "up" if chg > 0 else "down"
        sev = "success" if chg > 0 else "warning"
        insights.append((
            sev,
            f"Backend GMV **{direction} {abs(chg):.1f}%** vs prior period "
            f"({fmt_usd(pri_b_gmv)} → {fmt_usd(cur_b_gmv)}).",
        ))

# 4. Days with zero D1 purchases
n_zero = int(((fdf["d1_purchases"] == 0) | fdf["d1_purchases"].isna()).sum())
if n_zero > 0:
    pct_zero = n_zero / len(fdf) * 100
    sev = "warning" if pct_zero > 20 else "info"
    insights.append((
        sev,
        f"**{n_zero} day(s)** ({pct_zero:.0f}% of period) had 0 D1 purchases — "
        f"D1 ROAS is not meaningful on those days.",
    ))

# 5. Best day by backend ROI
valid_roi = fdf[fdf["backend_roi"].notna() & (fdf["backend_roi"] > 0)]
if not valid_roi.empty:
    best = valid_roi.loc[valid_roi["backend_roi"].idxmax()]
    insights.append((
        "info",
        f"Best backend ROI in period: **{best['backend_roi']:.2f}** on "
        f"**{best['date'].strftime('%d %b %Y')}** "
        f"(Spend {fmt_usd(best['spend'])}, GMV {fmt_usd(best['backend_gmv'])}, "
        f"Orders {int(best['backend_orders']) if not np.isnan(best['backend_orders']) else '—'}).",
    ))

# 6. CTR trend (first half vs second half of selected period)
if len(fdf) >= 6:
    mid = len(fdf) // 2
    ctr_first = fdf.iloc[:mid]["ctr"].mean()
    ctr_second = fdf.iloc[mid:]["ctr"].mean()
    if not np.isnan(ctr_first) and not np.isnan(ctr_second) and ctr_first > 0:
        ctr_chg = (ctr_second - ctr_first) / ctr_first * 100
        if abs(ctr_chg) > 10:
            direction = "improving" if ctr_chg > 0 else "declining"
            sev = "success" if ctr_chg > 0 else "warning"
            insights.append((
                sev,
                f"CTR is **{direction}** over the selected period "
                f"({fmt_pct(ctr_first)} → {fmt_pct(ctr_second)}, {ctr_chg:+.1f}%).",
            ))

if not insights:
    st.info("Select a longer date range to generate insights.")
else:
    for sev, text in insights:
        getattr(st, sev)(text)

st.divider()

# ---------------------------------------------------------------------------
# Raw data table
# ---------------------------------------------------------------------------

with st.expander("📋 Raw Data", expanded=False):
    display = fdf[list(DISPLAY_NAMES.keys())].copy()
    display["date"] = display["date"].dt.strftime("%Y-%m-%d")
    display.columns = list(DISPLAY_NAMES.values())
    st.dataframe(display, use_container_width=True, hide_index=True)
