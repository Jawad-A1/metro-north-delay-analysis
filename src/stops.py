"""Maps Metro-North GTFS stop_ids to human-readable station names.

The realtime feed (src/mta_live.py) only carries numeric stop_ids (e.g. "1"
for Grand Central). Station names come from MTA's static GTFS bundle, which
rarely changes, so we fetch it once and cache the mapping on disk.
"""

import csv
import io
import zipfile
from pathlib import Path

import requests

STATIC_GTFS_URL = "http://web.mta.info/developers/data/mnr/google_transit.zip"
STOPS_CACHE_PATH = Path("data/mnr_stops.csv")


def _fetch_and_cache_stop_names() -> dict[str, str]:
    response = requests.get(STATIC_GTFS_URL, timeout=30)
    response.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        with archive.open("stops.txt") as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
            stop_names = {row["stop_id"]: row["stop_name"] for row in reader}

    STOPS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with STOPS_CACHE_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["stop_id", "stop_name"])
        writer.writerows(stop_names.items())

    return stop_names


def load_stop_names() -> dict[str, str]:
    """Return a stop_id -> stop_name mapping, using a local cache when available."""
    if STOPS_CACHE_PATH.exists():
        with STOPS_CACHE_PATH.open(encoding="utf-8") as f:
            return {row["stop_id"]: row["stop_name"] for row in csv.DictReader(f)}
    return _fetch_and_cache_stop_names()
