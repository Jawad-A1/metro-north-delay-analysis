# Metro-North Delay Analysis

Explores historical MTA Metro-North delay data (`data/MTA_Metro-North_Delays__Beginning_2012_20260817.csv`)
and predicts whether a train is likely delayed right now.

## Setup

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Run everything through this venv - the system `python` won't have the required packages installed.

## Web UI

```
streamlit run src/app.py
```

Opens a browser page with a branch picker, live per-train delay status, and the
historical risk trend (including a per-hour risk chart), pulling from the same
`trends`/`mta_live`/`predict` modules as the CLI below.

## Live delay prediction (CLI)

```
python -m src.predict --branch Harlem [--train 401] [--now "2026-08-18T08:15:00"]
```

This combines two signals:

- **Live**: MTA's public Metro-North GTFS-realtime feed
  (`api-endpoint.mta.info/Dataservice/mtagtfsfeeds/mnr%2Fgtfs-mnr`) - no API key needed.
  It reports actual per-train delays (in minutes) once MTA's backend has matched a train
  to its schedule; trains running on time simply don't show up here. Each delayed train's
  *next upcoming stop* is shown with its scheduled and estimated clock time (the same
  numbers MTA's TrainTime app shows), taken from the feed's own predicted arrival time
  rather than a static schedule lookup.
- **Historical trend**: a relative delay-risk score (Low/Medium/High/Very High) per
  Branch/Period/hour, built in `src/trends.py`. Note the source CSV only logs delay
  *incidents* (Late/Cancelled/Terminated/Bus Substitution) - it has no record of
  on-time trips, so this is a relative risk score based on incident frequency and
  average minutes late, not a true statistical probability of delay.

## Files

- `src/explore.py` - basic exploration of the raw CSV.
- `src/trends.py` - builds the historical Branch/Period/hour delay-risk table.
- `src/mta_live.py` - fetches and parses the MTA GTFS-realtime trip-update feed.
- `src/predict.py` - CLI that combines live + historical signals into a prediction.
- `src/app.py` - Streamlit web UI wrapping the same prediction logic.
