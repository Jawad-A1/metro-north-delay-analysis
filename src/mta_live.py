"""Fetch and parse the MTA Metro-North GTFS-realtime trip-update feed.

Uses MTA's public GTFS feeds endpoint, which does not require an API key:
https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/mnr%2Fgtfs-mnr

The feed already includes a per-stop `delay` field (in seconds) for trains
MTA's backend has matched against the schedule and found running late -
there's no need to diff against the static GTFS schedule ourselves.
"""

import requests
from google.transit import gtfs_realtime_pb2

FEED_URL = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/mnr%2Fgtfs-mnr"

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
    """Extract delay info (in minutes) from trip updates in the feed.

    If branch is given, only trip updates on that branch's route_id are
    considered. If train_id is given, only trip updates whose trip_id or
    vehicle label contains it are returned. Only stop_time_updates that
    carry a populated delay field are returned (the feed only sets this
    field once MTA's backend has matched the trip to the schedule).
    """
    route_id = BRANCH_TO_ROUTE_ID.get(branch) if branch else None
    results = []
    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        trip_update = entity.trip_update
        trip_id = trip_update.trip.trip_id
        label = ""
        if entity.HasField("vehicle") and entity.vehicle.HasField("vehicle"):
            label = entity.vehicle.vehicle.label or entity.vehicle.vehicle.id

        if route_id and trip_update.trip.route_id != route_id:
            continue
        if train_id and train_id not in trip_id and train_id not in label:
            continue

        for stop_time_update in trip_update.stop_time_update:
            delay_seconds = None
            if stop_time_update.HasField("arrival") and stop_time_update.arrival.HasField("delay"):
                delay_seconds = stop_time_update.arrival.delay
            elif stop_time_update.HasField("departure") and stop_time_update.departure.HasField("delay"):
                delay_seconds = stop_time_update.departure.delay

            if delay_seconds is not None:
                results.append(
                    {
                        "trip_id": trip_id,
                        "train_label": label,
                        "route_id": trip_update.trip.route_id,
                        "branch": ROUTE_ID_TO_BRANCH.get(trip_update.trip.route_id),
                        "stop_id": stop_time_update.stop_id,
                        "delay_minutes": round(delay_seconds / 60, 1),
                    }
                )
    return results
