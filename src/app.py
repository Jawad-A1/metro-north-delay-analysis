"""Streamlit UI for the Metro-North delay predictor.

Run with:
    streamlit run src/app.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import trends
from src.predict import BRANCHES, get_current_time, infer_period
from src.mta_live import MtaLiveError, fetch_feed, find_live_delays, format_time, next_stop_per_trip
from src.stops import load_stop_names
from src.theme import CATEGORICAL, INK_SECONDARY, STATUS, apply_plotly_theme, risk_tier_style

PERIOD_ORDER = ["AM Peak", "PM Peak", "Off-Peak"]
PERIOD_COLORS = dict(zip(PERIOD_ORDER, CATEGORICAL))
LIVE_REFRESH_SECONDS = 30

apply_plotly_theme()

st.set_page_config(page_title="Metro-North Delay Predictor", layout="centered")

st.title("Metro-North Delay Predictor")
st.caption("Live MTA status, a real historical delay probability, and a relative delay-risk trend, side by side.")

branch = st.selectbox("Branch", BRANCHES)

now = get_current_time()
period = infer_period(now)
hour = now.hour

st.caption(f"Bucketed as **{period}**, hour {hour}")


@st.cache_data(ttl=LIVE_REFRESH_SECONDS)
def get_live_delays(branch: str):
    """Fetch the live GTFS feed and return current delays for a branch."""
    feed = fetch_feed()
    return find_live_delays(feed, branch=branch)


@st.cache_data(ttl=3600)
def get_historical_stats():
    """Load and aggregate the historical delay-risk stats, cached for an hour."""
    df = trends.load_delay_data()
    return trends.build_hourly_branch_period_stats(df)


@st.cache_data(ttl=3600)
def get_otp_stats():
    """Load and aggregate MTA's official on-time-performance stats, cached for an hour."""
    df = trends.load_otp_data()
    return trends.build_otp_period_stats(df)


@st.cache_data(ttl=86400)
def get_stop_names():
    """Load the stop_id -> stop_name mapping, cached for a day."""
    return load_stop_names()


def _minutes_late_wash(value: float) -> str:
    """Light background wash keyed to the fixed status ramp (never the sole cue -
    the minutes-late number itself is always shown alongside it)."""
    if value >= 30:
        bg = STATUS["critical"]
    elif value >= 15:
        bg = STATUS["serious"]
    elif value >= 5:
        bg = STATUS["warning"]
    else:
        bg = STATUS["good"]
    return f"background-color: {bg}1f;"


@st.fragment(run_every=LIVE_REFRESH_SECONDS)
def render_live_status(branch: str) -> None:
    live_now = get_current_time()
    with st.container(border=True):
        st.subheader("Live status")
        st.caption(
            f"Auto-refreshes every {LIVE_REFRESH_SECONDS}s - last checked "
            f"{live_now.strftime('%I:%M:%S %p')}"
        )
        try:
            live_delays = get_live_delays(branch)
            if live_delays:
                stop_names = get_stop_names()
                next_stops = next_stop_per_trip(live_delays, live_now)
                live_df = pd.DataFrame(
                    [
                        {
                            "Train": d["train_label"] or d["trip_id"],
                            "Next stop": stop_names.get(d["stop_id"], d["stop_id"]),
                            "Scheduled": format_time(d["scheduled_time"]) if d["scheduled_time"] else "-",
                            "Estimated": format_time(d["estimated_time"]) if d["estimated_time"] else "-",
                            "Minutes late": d["delay_minutes"],
                        }
                        for d in next_stops
                    ]
                ).sort_values("Minutes late", ascending=False)

                col_count, col_table = st.columns([1, 4])
                col_count.metric("Delayed trains", len(live_df))
                styled = (
                    live_df.style.map(_minutes_late_wash, subset=["Minutes late"])
                    .format({"Minutes late": "{:.1f} min"})
                )
                col_table.dataframe(styled, hide_index=True, width="stretch")
            else:
                st.success(f"No active delays reported for {branch} right now.")
        except MtaLiveError as exc:
            st.error(f"Live feed unavailable: {exc}")


render_live_status(branch)

with st.container(border=True):
    st.subheader("Delay probability")
    otp_stats = get_otp_stats()
    prob = trends.lookup_delay_probability(otp_stats, branch=branch, period=period)

    if prob:
        col1, col2 = st.columns(2)
        col1.metric(f"{prob['period']} delay probability", f"{prob['delay_probability_pct']}%")
        col2.metric("Avg on-time performance", f"{prob['avg_on_time_pct']}%")
        proxy_note = (
            f" Proxied via the combined {prob['otp_branch']} Line figure "
            "(MTA's OTP dataset doesn't break out this sub-branch)."
            if prob["is_proxied"]
            else ""
        )
        st.caption(
            f"Based on {prob['months']} months of MTA's official On-Time Performance data "
            f"(arrivals within 5:59 of schedule).{proxy_note}"
        )
    else:
        st.info("No on-time-performance data for this branch/period.")

with st.container(border=True):
    st.subheader("Historical trend")
    stats = get_historical_stats()
    row = trends.lookup_risk(stats, branch=branch, period=period, hour=hour)

    if row:
        color, icon = risk_tier_style(row["risk_tier"])
        st.markdown(
            f"""<div style="display:inline-flex;align-items:center;gap:8px;
                padding:6px 14px;border-radius:999px;background:{color}1a;
                border:1px solid {color}55;font-weight:600;color:var(--text-color);
                margin-bottom:8px;">
                <span>{icon}</span><span>{row['risk_tier']} relative risk</span>
                </div>""",
            unsafe_allow_html=True,
        )
        col1, col2 = st.columns(2)
        col1.metric("Historical delay incidents in this slot", row["incident_count"])
        col2.metric("Avg minutes late when delayed", row["avg_minutes_late"])
        st.caption(
            "This is a relative frequency score across hours, not a probability - the "
            "incident log only records delay incidents (Late/Cancelled/Terminated/Bus "
            "Substitution), not on-time trips. See Delay probability above for a true probability."
        )
    else:
        st.info("No historical data for this branch/period/hour combination.")

    st.markdown(f"**Risk by hour - {branch}**")
    branch_stats = stats[stats["Branch"] == branch]
    chart_df = branch_stats.pivot_table(index="Hour", columns="Period", values="risk_score", aggfunc="mean")

    fig_risk = go.Figure()
    for p in PERIOD_ORDER:
        if p not in chart_df.columns:
            continue
        fig_risk.add_trace(
            go.Bar(
                x=chart_df.index,
                y=chart_df[p],
                name=p,
                marker_color=PERIOD_COLORS[p],
                hovertemplate=f"%{{x}}:00 · {p}<br>Risk score %{{y:.2f}}<extra></extra>",
            )
        )
    fig_risk.add_vline(
        x=hour,
        line_dash="dash",
        line_color=INK_SECONDARY,
        annotation_text="Now",
        annotation_font_color=INK_SECONDARY,
    )
    fig_risk.update_layout(
        barmode="group",
        height=320,
        bargap=0.25,
        bargroupgap=0.05,
        xaxis_title="Hour of day",
        yaxis_title="Relative risk score",
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1),
    )
    st.plotly_chart(fig_risk, width="stretch")
