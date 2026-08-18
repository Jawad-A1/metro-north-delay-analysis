"""Fetch and parse the MTA Metro-North GTFS-realtime trip-update feed.

Uses MTA's public GTFS feeds endpoint, which does not require an API key:
https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/mnr%2Fgtfs-mnr

The feed already includes, per stop, both a `delay` field (seconds) and an
absolute predicted `time` field (epoch seconds) once MTA's backend has
matched a train to its schedule - that `time` field *is* the estimated
clock time MTA's TrainTime app shows, so we use it directly rather than
re-deriving it by diffing against the static GTFS schedule ourselves.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests
from google.transit import gtfs_realtime_pb2

FEED_URL = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/mnr%2Fgtfs-mnr"
NY_TZ = ZoneInfo("America/New_York")

# route_id -> Branch name, from MNR's static GTFS routes.txt
ROUTE_ID_TO_BRANCH = {
    "1": "Hudson",
    "2": "Harlem",
    "3": "New Haven Mainline",
    "4": "New Canaan",
    "5": "Danbury",
    "6": "Waterbury",
}
BRANCH_TO_ROUTE_ID = {branch: route_id for route_id, branch in ROUTE_ID_TO_BRANCH.items()}


class MtaLiveError(RuntimeError):
    """Raised when the live feed can't be fetched or parsed."""


def fetch_feed(timeout: float = 10.0) -> gtfs_realtime_pb2.FeedMessage:
    try:
        response = requests.get(FEED_URL, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise MtaLiveError(f"Failed to fetch MTA live feed: {exc}") from exc

    feed = gtfs_realtime_pb2.FeedMessage()
    try:
        feed.ParseFromString(response.content)
    except Exception as exc:
        raise MtaLiveError(f"Failed to parse MTA GTFS-realtime feed: {exc}") from exc
    return feed


def find_live_delays(
    feed: gtfs_realtime_pb2.FeedMessage,
    branch: str | None = None,
    train_id: str | None = None,
) -> list[dict]:
    """Extract delay info from trip updates in the feed.

    If branch is given, only trip updates on that branch's route_id are
    considered. If train_id is given, only trip updates whose trip_id or
    vehicle label contains it are returned. Only stop_time_updates that
    carry a populated delay field are returned (the feed only sets this
    field once MTA's backend has matched the trip to the schedule) - each
    entry also carries the matching `estimated_time`/`scheduled_time` for
    that stop, taken from the feed's own predicted arrival/departure time.

    A trip typically has one entry per remaining stop (past and future) in
    the feed; use `next_stop_per_trip` to collapse that down to the single
    upcoming stop per train, matching what TrainTime shows for a train
    already underway.
    """
    route_id = BRANCH_TO_ROUTE_ID.get(branch) if branch else None
    results = []
    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        trip_update = entity.trip_update
        trip_id = trip_update.trip.trip_id
        this_route_id = trip_update.trip.route_id
        label = ""
        if entity.HasField("vehicle") and entity.vehicle.HasField("vehicle"):
            label = entity.vehicle.vehicle.label or entity.vehicle.vehicle.id

        if route_id and this_route_id != route_id:
            continue
        if train_id and train_id not in trip_id and train_id not in label:
            continue

        for stop_time_update in trip_update.stop_time_update:
            event = None
            if stop_time_update.HasField("arrival") and stop_time_update.arrival.HasField("delay"):
                event = stop_time_update.arrival
            elif stop_time_update.HasField("departure") and stop_time_update.departure.HasField("delay"):
                event = stop_time_update.departure

            if event is None:
                continue

            delay_seconds = event.delay
            estimated_time = None
            scheduled_time = None
            if event.HasField("time"):
                estimated_time = datetime.fromtimestamp(event.time, tz=timezone.utc).astimezone(NY_TZ)
                scheduled_time = estimated_time - timedelta(seconds=delay_seconds)

            results.append(
                {
                    "trip_id": trip_id,
                    "train_label": label,
                    "route_id": this_route_id,
                    "branch": ROUTE_ID_TO_BRANCH.get(this_route_id),
                    "stop_id": stop_time_update.stop_id,
                    "delay_minutes": round(delay_seconds / 60, 1),
                    "scheduled_time": scheduled_time,
                    "estimated_time": estimated_time,
                }
            )
    return results


def next_stop_per_trip(live_delays: list[dict], now: datetime) -> list[dict]:
    """Collapse per-stop delay entries down to one entry per trip: the
    upcoming stop (soonest estimated time at or after `now`), matching what
    TrainTime shows for an in-progress train, instead of an arbitrary
    already-passed stop from earlier in the feed's per-trip stop list.
    Falls back to the latest available stop if every update for a trip is
    already in the past.
    """
    best: dict[str, dict] = {}
    for d in live_delays:
        trip_id = d["trip_id"]
        current = best.get(trip_id)
        if current is None:
            best[trip_id] = d
            continue

        candidate_time = d["estimated_time"]
        current_time = current["estimated_time"]
        if candidate_time is None or current_time is None:
            continue

        candidate_upcoming = candidate_time >= now
        current_upcoming = current_time >= now
        if candidate_upcoming and not current_upcoming:
            best[trip_id] = d
        elif candidate_upcoming and current_upcoming and candidate_time < current_time:
            best[trip_id] = d
        elif not candidate_upcoming and not current_upcoming and candidate_time > current_time:
            best[trip_id] = d
    return list(best.values())


def format_time(dt: datetime) -> str:
    """Format an aware datetime as e.g. '8:15 AM' for display."""
    return dt.strftime("%I:%M %p").lstrip("0")
