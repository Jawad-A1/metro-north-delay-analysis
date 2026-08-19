"""Streamlit dashboard for exploring historical Metro-North delay incidents.

Run with:
    streamlit run app.py
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.theme import BLUE, CATEGORICAL, INK_SECONDARY, apply_plotly_theme

DATA_PATH = "data/MTA_Metro-North_Delays__Beginning_2012_20260817.csv"

apply_plotly_theme()

st.set_page_config(page_title="Metro-North Delay Analysis", layout="wide")


@st.cache_data
def load_data(path: str) -> pd.DataFrame:
    """Load the delay CSV and parse its date/numeric columns."""
    df = pd.read_csv(path)
    df["Service Date"] = pd.to_datetime(df["Service Date"], format="%m/%d/%Y")
    df["Minutes Late"] = pd.to_numeric(df["Minutes Late"], errors="coerce")
    return df


df = load_data(DATA_PATH)

# ---------------- Sidebar filters ----------------
st.sidebar.header("Filters")

min_date, max_date = df["Service Date"].min().date(), df["Service Date"].max().date()
date_range = st.sidebar.date_input(
    "Service date range", value=(min_date, max_date), min_value=min_date, max_value=max_date
)
if isinstance(date_range, tuple) and len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date, end_date = min_date, max_date

branches = st.sidebar.multiselect(
    "Branch", sorted(df["Branch"].unique()), default=sorted(df["Branch"].unique())
)
periods = st.sidebar.multiselect(
    "Period", sorted(df["Period"].unique()), default=sorted(df["Period"].unique())
)
statuses = st.sidebar.multiselect(
    "Status", sorted(df["Status"].unique()), default=sorted(df["Status"].unique())
)
categories = st.sidebar.multiselect(
    "Delay category", sorted(df["Delay Category"].unique()), default=sorted(df["Delay Category"].unique())
)

max_minutes = int(df["Minutes Late"].max())
minutes_range = st.sidebar.slider("Minutes late (where recorded)", 0, max_minutes, (0, max_minutes))

mask = (
    (df["Service Date"].dt.date >= start_date)
    & (df["Service Date"].dt.date <= end_date)
    & (df["Branch"].isin(branches))
    & (df["Period"].isin(periods))
    & (df["Status"].isin(statuses))
    & (df["Delay Category"].isin(categories))
    & (
        # Keep rows with no recorded minutes (e.g. cancellations) regardless of the slider.
        df["Minutes Late"].isna()
        | df["Minutes Late"].between(minutes_range[0], minutes_range[1])
    )
)
fdf = df[mask]

st.title("Metro-North Delay Analysis")
st.caption(
    f"{len(fdf):,} incidents from {start_date:%b %d, %Y} to {end_date:%b %d, %Y} "
    f"across {fdf['Branch'].nunique()} branches"
)

if fdf.empty:
    st.warning("No incidents match the current filters.")
    st.stop()

# ---------------- KPI row ----------------
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total incidents", f"{len(fdf):,}")
c2.metric("Avg minutes late", f"{fdf['Minutes Late'].mean():.1f}")
c3.metric("Median minutes late", f"{fdf['Minutes Late'].median():.0f}")
disruption = fdf["Status"].isin(["Cancelled", "Terminated", "Bus Substitution"]).mean()
c4.metric("Cancelled / terminated / bus sub", f"{disruption:.1%}")
c5.metric("Top delay cause", fdf["Delay Category"].value_counts().idxmax())

st.divider()

# ---------------- Trend over time ----------------
st.subheader("Incidents over time")
freq_label = st.radio("Aggregate by", ["Month", "Year"], horizontal=True, label_visibility="collapsed")
freq = "ME" if freq_label == "Month" else "YE"  # pandas resample codes: month-end / year-end
trend = fdf.set_index("Service Date").resample(freq).size().reset_index(name="Incidents")

fig_trend = go.Figure(
    go.Scatter(
        x=trend["Service Date"],
        y=trend["Incidents"],
        mode="lines",
        line=dict(color=BLUE, width=2, shape="spline"),
        fill="tozeroy",
        fillcolor="rgba(42,120,214,0.12)",
        hovertemplate="%{x|%b %Y}<br>%{y:,} incidents<extra></extra>",
    )
)
fig_trend.update_layout(height=320, xaxis_title=None, yaxis_title="Incidents")
st.plotly_chart(fig_trend, width='stretch')

st.divider()

# ---------------- Branch + Delay category ----------------
col1, col2 = st.columns(2)

with col1:
    st.subheader("Incidents by branch")
    by_branch = fdf["Branch"].value_counts().sort_values(ascending=True)
    fig_branch = go.Figure(
        go.Bar(
            x=by_branch.values,
            y=by_branch.index,
            orientation="h",
            marker_color=BLUE,
            text=[f"{v:,}" for v in by_branch.values],
            textposition="outside",
            hovertemplate="%{y}<br>%{x:,} incidents<extra></extra>",
        )
    )
    fig_branch.update_layout(height=320, xaxis_title="Incidents", yaxis_title=None, showlegend=False)
    st.plotly_chart(fig_branch, width='stretch')

with col2:
    st.subheader("Incidents by delay category")
    by_cat = fdf["Delay Category"].value_counts().sort_values(ascending=True)
    colors = (CATEGORICAL * ((len(by_cat) // len(CATEGORICAL)) + 1))[: len(by_cat)]
    fig_cat = go.Figure(
        go.Bar(
            x=by_cat.values,
            y=by_cat.index,
            orientation="h",
            marker_color=colors,
            text=[f"{v:,}" for v in by_cat.values],
            textposition="outside",
            hovertemplate="%{y}<br>%{x:,} incidents<extra></extra>",
        )
    )
    fig_cat.update_layout(height=320, xaxis_title="Incidents", yaxis_title=None, showlegend=False)
    st.plotly_chart(fig_cat, width='stretch')

st.divider()

# ---------------- Period + Status ----------------
col3, col4 = st.columns(2)

with col3:
    st.subheader("Incidents by period")
    by_period = fdf["Period"].value_counts()
    fig_period = go.Figure(
        go.Bar(
            x=by_period.index,
            y=by_period.values,
            marker_color=CATEGORICAL[: len(by_period)],
            text=[f"{v:,}" for v in by_period.values],
            textposition="outside",
            hovertemplate="%{x}<br>%{y:,} incidents<extra></extra>",
        )
    )
    fig_period.update_layout(height=300, xaxis_title=None, yaxis_title="Incidents", showlegend=False)
    st.plotly_chart(fig_period, width='stretch')

with col4:
    st.subheader("Incidents by status")
    by_status = fdf["Status"].value_counts()
    fig_status = go.Figure(
        go.Bar(
            x=by_status.index,
            y=by_status.values,
            marker_color=CATEGORICAL[: len(by_status)],
            text=[f"{v:,}" for v in by_status.values],
            textposition="outside",
            hovertemplate="%{x}<br>%{y:,} incidents<extra></extra>",
        )
    )
    fig_status.update_layout(height=300, xaxis_title=None, yaxis_title="Incidents", showlegend=False)
    st.plotly_chart(fig_status, width='stretch')

st.divider()

# ---------------- Top locations ----------------
st.subheader("Top 15 locations by incident count")
top_loc = fdf["Location Name"].value_counts().head(15).sort_values(ascending=True)
fig_loc = go.Figure(
    go.Bar(
        x=top_loc.values,
        y=top_loc.index,
        orientation="h",
        marker_color=BLUE,
        text=[f"{v:,}" for v in top_loc.values],
        textposition="outside",
        hovertemplate="%{y}<br>%{x:,} incidents<extra></extra>",
    )
)
fig_loc.update_layout(height=440, xaxis_title="Incidents", yaxis_title=None, showlegend=False)
st.plotly_chart(fig_loc, width='stretch')

st.divider()

# ---------------- Minutes late distribution ----------------
st.subheader("Minutes late distribution")
late = fdf["Minutes Late"].dropna()
fig_hist = go.Figure(
    go.Histogram(
        x=late,
        marker_color=BLUE,
        xbins=dict(start=0, end=max(late.max(), 10), size=5),
        hovertemplate="%{x} min<br>%{y:,} incidents<extra></extra>",
    )
)
fig_hist.add_vline(x=late.median(), line_dash="dash", line_color=INK_SECONDARY,
                    annotation_text=f"Median {late.median():.0f} min", annotation_font_color=INK_SECONDARY)
fig_hist.update_layout(height=320, xaxis_title="Minutes late", yaxis_title="Incidents", showlegend=False)
st.plotly_chart(fig_hist, width='stretch')

st.divider()

# ---------------- Raw data ----------------
st.subheader("Filtered data")
st.dataframe(fdf, width='stretch', height=320)
st.download_button(
    "Download filtered data as CSV",
    fdf.to_csv(index=False).encode("utf-8"),
    file_name="metro_north_delays_filtered.csv",
    mime="text/csv",
)
