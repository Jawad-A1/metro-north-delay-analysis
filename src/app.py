"""Streamlit UI for the Metro-North delay predictor.

Run with:
    streamlit run src/app.py
"""

import pandas as pd
import streamlit as st

from src import trends
from src.predict import BRANCHES, get_current_time, infer_period
from src.mta_live import MtaLiveError, fetch_feed, find_live_delays, format_time, next_stop_per_trip
from src.stops import load_stop_names

st.set_page_config(page_title="Metro-North Delay Predictor", page_icon="🚆", layout="centered")

st.title("🚆 Metro-North Delay Predictor")

branch = st.selectbox("Branch", BRANCHES)
refresh = st.button("Refresh live data")

now = get_current_time()
period = infer_period(now)
hour = now.hour

st.caption(f"Current time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')} — bucketed as **{period}**, hour {hour}")


@st.cache_data(ttl=30)
def get_live_delays(branch: str, _cache_bust: int):
    feed = fetch_feed()
    return find_live_delays(feed, branch=branch)


@st.cache_data(ttl=3600)
def get_historical_stats():
    df = trends.load_delay_data()
    return trends.build_hourly_branch_period_stats(df)


@st.cache_data(ttl=86400)
def get_stop_names():
    return load_stop_names()


st.subheader("Live status")
try:
    cache_bust = 0 if not refresh else pd.Timestamp.now().value
    live_delays = get_live_delays(branch, cache_bust)
    if live_delays:
        stop_names = get_stop_names()
        next_stops = next_stop_per_trip(live_delays, now)
        live_df = pd.DataFrame(
            [
                {
                    "Train": d["train_label"] or d["trip_id"],
                    "Next stop": stop_names.get(d["stop_id"], d["stop_id"]),
                    "Scheduled": format_time(d["scheduled_time"]) if d["scheduled_time"] else "—",
                    "Estimated": format_time(d["estimated_time"]) if d["estimated_time"] else "—",
                    "Minutes late": d["delay_minutes"],
                }
                for d in next_stops
            ]
        ).sort_values("Minutes late", ascending=False)
        st.dataframe(live_df, hide_index=True, width="stretch")
        st.warning(f"{len(live_df)} train(s) on {branch} currently reporting a delay.")
    else:
        st.success(f"No active delays reported for {branch} right now.")
except MtaLiveError as exc:
    st.error(f"Live feed unavailable: {exc}")

st.subheader("Historical trend")
stats = get_historical_stats()
row = trends.lookup_risk(stats, branch=branch, period=period, hour=hour)

if row:
    tier_color = {"Low": "green", "Medium": "orange", "High": "red", "Very High": "red"}
    color = tier_color.get(row["risk_tier"], "gray")
    st.markdown(f"Risk tier: **:{color}[{row['risk_tier']}]**")
    col1, col2 = st.columns(2)
    col1.metric("Historical delay incidents in this slot", row["incident_count"])
    col2.metric("Avg minutes late when delayed", row["avg_minutes_late"])
    st.caption(
        "This is a relative risk score, not a probability - the source data only "
        "logs delay incidents (Late/Cancelled/Terminated/Bus Substitution), not on-time trips."
    )
else:
    st.info("No historical data for this branch/period/hour combination.")

st.subheader(f"Risk by hour — {branch}")
branch_stats = stats[stats["Branch"] == branch]
chart_df = branch_stats.pivot_table(index="Hour", columns="Period", values="risk_score", aggfunc="mean")
st.bar_chart(chart_df)
