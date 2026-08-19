"""Historical delay-risk trends derived from the MTA Metro-North delay log.

The source CSV only records delay *incidents* (Late/Cancelled/Terminated/Bus
Substitution) - it has no record of on-time trips. That means we cannot
compute a true "probability a train is delayed" (there is no on-time
denominator). Instead we build a relative risk score per
(Branch, Period, hour-of-day) bucket from incident frequency and average
minutes late, and bucket it into Low/Medium/High/Very High tiers.
"""

import pandas as pd

DATA_PATH = "data/MTA_Metro-North_Delays__Beginning_2012_20260817.csv"

RISK_TIERS = ["Low", "Medium", "High", "Very High"]


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


if __name__ == "__main__":
    df = load_delay_data()
    stats = build_hourly_branch_period_stats(df)
    print(stats.sort_values("risk_score", ascending=False).head(10).to_string(index=False))
