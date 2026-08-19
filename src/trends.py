"""Historical delay trends derived from two MTA Metro-North datasets.

The incident-log CSV only records delay *incidents*
(Late/Cancelled/Terminated/Bus Substitution) - it has no record of on-time
trips, so incident counts alone can't yield a true "probability a train is
delayed" (there is no on-time denominator). We still use it to build a
relative risk score per (Branch, Period, hour-of-day) bucket from incident
frequency and average minutes late, bucketed into Low/Medium/High/Very High
tiers - useful for seeing which hours are relatively worse, but not a real
probability.

For an actual probability, we use MTA's official On-Time Performance
dataset (monthly On-Time % per Branch/Period since 2020, published at
https://data.ny.gov/Transportation/MTA-Metro-North-On-Time-Performance-Beginning-2020/83hw-i6xw).
Averaging its on-time percentage across all available months per
Branch/Period and taking 1 - on_time_rate gives a true historical delay
probability, at Period granularity (it doesn't break down by hour, and its
New Haven Line figure isn't split into the New Canaan/Danbury/Waterbury
sub-branches - those three are proxied by the combined New Haven number).
"""

import pandas as pd

DATA_PATH = "data/MTA_Metro-North_Delays__Beginning_2012_20260817.csv"
OTP_DATA_PATH = "data/MTA_Metro-North_On-Time_Performance_Beginning_2020.csv"

RISK_TIERS = ["Low", "Medium", "High", "Very High"]

# Incident-log Branch -> On-Time Performance dataset branch_line. The OTP
# dataset doesn't break out the New Haven Line's sub-branches, so New
# Canaan/Danbury/Waterbury are proxied by the combined New Haven figure.
OTP_BRANCH_MAP = {
    "Harlem": "Harlem",
    "Hudson": "Hudson",
    "New Haven Mainline": "New Haven",
    "New Canaan": "New Haven",
    "Danbury": "New Haven",
    "Waterbury": "New Haven",
}

PERIOD_TO_OTP_COLUMN = {
    "AM Peak": "am_peak",
    "PM Peak": "pm_peak",
    "Off-Peak": "off_peak",
}


def load_delay_data(csv_path: str = DATA_PATH) -> pd.DataFrame:
    """Load the delay CSV and derive an hour-of-day column from Depart Time."""
    df = pd.read_csv(csv_path)
    df["Depart Time"] = pd.to_datetime(df["Depart Time"], errors="coerce")
    df["Hour"] = df["Depart Time"].dt.hour
    return df


def build_hourly_branch_period_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate incident count and average minutes late per Branch/Period/Hour."""
    grouped = (
        df.dropna(subset=["Hour"])
        .groupby(["Branch", "Period", "Hour"])
        .agg(incident_count=("Status", "count"), avg_minutes_late=("Minutes Late", "mean"))
        .reset_index()
    )
    grouped["Hour"] = grouped["Hour"].astype(int)

    # Relative risk score: normalize incident_count against the busiest bucket
    # for the same branch, so risk is comparable across branches with very
    # different overall record counts.
    max_by_branch = grouped.groupby("Branch")["incident_count"].transform("max")
    grouped["risk_score"] = grouped["incident_count"] / max_by_branch

    grouped["risk_tier"] = pd.cut(
        grouped["risk_score"],
        bins=[-0.001, 0.25, 0.5, 0.75, 1.0],  # -0.001 so a risk_score of exactly 0 falls in "Low"
        labels=RISK_TIERS,
    )
    return grouped


def lookup_risk(stats: pd.DataFrame, branch: str, period: str, hour: int) -> dict | None:
    """Look up the risk bucket for a given branch/period/hour, or None if no data."""
    match = stats[
        (stats["Branch"] == branch) & (stats["Period"] == period) & (stats["Hour"] == hour)
    ]
    if match.empty:
        return None
    row = match.iloc[0]
    return {
        "branch": branch,
        "period": period,
        "hour": hour,
        "incident_count": int(row["incident_count"]),
        "avg_minutes_late": round(float(row["avg_minutes_late"]), 1),
        "risk_score": round(float(row["risk_score"]), 2),
        "risk_tier": str(row["risk_tier"]),
    }


def load_otp_data(csv_path: str = OTP_DATA_PATH) -> pd.DataFrame:
    """Load MTA's official monthly On-Time Performance dataset."""
    df = pd.read_csv(csv_path)
    df["month"] = pd.to_datetime(df["month"])
    return df


def build_otp_period_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Average on-time % by branch_line/period across all available months,
    then convert to a true delay probability (1 - on-time rate). This is a
    real probability, unlike the incident-count risk_score above, but only
    at Period granularity (no hour-of-day breakdown in the source data)."""
    rows = []
    for otp_branch, group in df.groupby("branch_line"):
        for period, column in PERIOD_TO_OTP_COLUMN.items():
            values = group[column].dropna() if column in group else pd.Series(dtype=float)
            if values.empty:
                continue
            avg_otp = values.mean()
            rows.append(
                {
                    "otp_branch": otp_branch,
                    "period": period,
                    "avg_on_time_rate": avg_otp,
                    "delay_probability": 1 - avg_otp,
                    "months": int(values.count()),
                }
            )
    return pd.DataFrame(rows)


def lookup_delay_probability(otp_stats: pd.DataFrame, branch: str, period: str) -> dict | None:
    """Look up the true historical delay probability for a branch/period,
    sourced from MTA's on-time-performance dataset (see module docstring),
    or None if the branch/period isn't covered."""
    otp_branch = OTP_BRANCH_MAP.get(branch)
    if otp_branch is None:
        return None
    match = otp_stats[(otp_stats["otp_branch"] == otp_branch) & (otp_stats["period"] == period)]
    if match.empty:
        return None
    row = match.iloc[0]
    return {
        "branch": branch,
        "otp_branch": otp_branch,
        "is_proxied": otp_branch != branch,
        "period": period,
        "avg_on_time_pct": round(float(row["avg_on_time_rate"]) * 100, 1),
        "delay_probability_pct": round(float(row["delay_probability"]) * 100, 1),
        "months": int(row["months"]),
    }


if __name__ == "__main__":
    df = load_delay_data()
    stats = build_hourly_branch_period_stats(df)
    print(stats.sort_values("risk_score", ascending=False).head(10).to_string(index=False))

    otp_df = load_otp_data()
    otp_stats = build_otp_period_stats(otp_df)
    print()
    print(otp_stats.sort_values("delay_probability", ascending=False).to_string(index=False))
