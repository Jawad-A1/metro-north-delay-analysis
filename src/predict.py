"""Predict whether a Metro-North train is likely delayed right now.

Combines two signals:
  1. Live MTA GTFS-realtime feed (ground truth; no API key needed) - actual
     reported delay, if any, for trains on the given branch.
  2. Historical delay-risk trend for the current Branch/Period/hour, built
     from src/trends.py.

Usage:
    python -m src.predict --branch Harlem [--train 401] [--now "2026-08-18 08:15"]
"""

import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

from src import trends
from src.mta_live import MtaLiveError, fetch_feed, find_live_delays, format_time, next_stop_per_trip
from src.stops import load_stop_names

NY_TZ = ZoneInfo("America/New_York")
BRANCHES = ["Harlem", "Hudson", "New Haven Mainline", "New Canaan", "Danbury", "Waterbury"]


def get_current_time(override: str | None = None) -> datetime:
    if override:
        return datetime.fromisoformat(override).replace(tzinfo=NY_TZ)
    return datetime.now(NY_TZ)


def infer_period(now: datetime) -> str:
    """Heuristic bucket matching the CSV's Period labels.

    Weekday mornings (6-10am) and evenings (4-8pm) are treated as peak;
    everything else (including weekends) is off-peak. This is an
    approximation of MTA's actual peak-fare schedule, not an official source.
    """
    if now.weekday() >= 5:  # Saturday/Sunday
        return "Off-Peak"
    if 6 <= now.hour < 10:
        return "AM Peak"
    if 16 <= now.hour < 20:
        return "PM Peak"
    return "Off-Peak"


def predict(branch: str, now: datetime, train_id: str | None = None) -> dict:
    period = infer_period(now)
    hour = now.hour

    live_delays = []
    live_error = None
    try:
        feed = fetch_feed()
        live_delays = find_live_delays(feed, branch=branch, train_id=train_id)
    except MtaLiveError as exc:
        live_error = str(exc)

    df = trends.load_delay_data()
    stats = trends.build_hourly_branch_period_stats(df)
    historical = trends.lookup_risk(stats, branch=branch, period=period, hour=hour)

    return {
        "branch": branch,
        "now": now.isoformat(),
        "now_dt": now,
        "period": period,
        "hour": hour,
        "live_delays": live_delays,
        "live_error": live_error,
        "historical": historical,
    }


def render(result: dict) -> str:
    lines = [
        f"Branch: {result['branch']}",
        f"Current time: {result['now']} (bucketed as {result['period']}, hour {result['hour']})",
        "",
    ]

    if result["live_delays"]:
        lines.append("LIVE: MTA feed reports active delays:")
        stop_names = load_stop_names()
        next_stops = next_stop_per_trip(result["live_delays"], result["now_dt"])
        for d in sorted(next_stops, key=lambda d: d["delay_minutes"], reverse=True):
            next_stop = stop_names.get(d["stop_id"], d["stop_id"])
            time_info = ""
            if d["estimated_time"]:
                time_info = (
                    f", due {format_time(d['estimated_time'])}"
                    f" (scheduled {format_time(d['scheduled_time'])})"
                )
            lines.append(
                f"  - train {d['train_label'] or d['trip_id']} ({d['branch']}): "
                f"{d['delay_minutes']} min late (next stop {next_stop}{time_info})"
            )
    elif result["live_error"]:
        lines.append(f"LIVE: unavailable ({result['live_error']})")
    else:
        lines.append("LIVE: MTA feed reports no active delay for this train/branch right now.")

    lines.append("")

    h = result["historical"]
    if h:
        lines.append(
            f"HISTORICAL TREND: {h['risk_tier']} delay risk for {h['branch']} during "
            f"{h['period']} around {h['hour']}:00 "
            f"({h['incident_count']} historical delay incidents in this slot, "
            f"averaging {h['avg_minutes_late']} min late when delayed)."
        )
        lines.append(
            "Note: this is a relative risk score, not a probability - the source data "
            "only logs delay incidents, not on-time trips."
        )
    else:
        lines.append("HISTORICAL TREND: no historical data for this branch/period/hour combination.")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--branch", required=True, choices=BRANCHES)
    parser.add_argument("--train", default=None, help="Train ID/number to match in the live feed")
    parser.add_argument(
        "--now",
        default=None,
        help="Override current time, ISO format e.g. '2026-08-18T08:15:00' (for testing)",
    )
    args = parser.parse_args()

    now = get_current_time(args.now)
    result = predict(args.branch, now, train_id=args.train)
    print(render(result))


if __name__ == "__main__":
    main()
