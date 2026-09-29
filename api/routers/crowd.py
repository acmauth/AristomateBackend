from fastapi import APIRouter, Query
import asyncio
import os
from typing import Optional
import requests
from dotenv import load_dotenv
import httpx
import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo
from fastapi import Query, HTTPException

router = APIRouter()
load_dotenv()

API_KEY = os.getenv('CROWD_API_KEY')



BIN_MINUTES = 5
HISTORY_DAYS = 28
MIN_SAMPLES = 50                 # min. windows needed for a per-period baseline
LOCAL_TZ = ZoneInfo("Europe/Athens")
TIMESTAMPS_ARE_LOCAL = True      # API sends local wall-clock time with a fake "Z"

# Open periods in local time, minutes since midnight, end exclusive.
# Closed: 10:30-12:30, 16:30-18:00, 21:00-08:00
PERIODS = {
    "breakfast": (8 * 60, 10 * 60 + 30),
    "lunch": (12 * 60 + 30, 16 * 60 + 30),
    "dinner": (18 * 60, 21 * 60),
}


def period_labels(index: pd.DatetimeIndex) -> pd.Series:
    """Label each bin by its meal period (None when closed). Index = naive local time."""
    minutes = index.hour * 60 + index.minute
    labels = pd.Series([None] * len(index), index=index, dtype="object")
    for name, (start, end) in PERIODS.items():
        labels.loc[(minutes >= start) & (minutes < end)] = name
    return labels


def to_api_time(dt_local: datetime) -> str:
    """Format a naive local datetime the way the API expects it."""
    if not TIMESTAMPS_ARE_LOCAL:
        dt_local = dt_local.replace(tzinfo=LOCAL_TZ).astimezone(timezone.utc)
    return dt_local.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def extract_rows(body) -> list:
    """Return the list of visit rows, unwrapping common envelope shapes."""
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for key in ("data", "Data", "result", "results", "items", "visits"):
            if isinstance(body.get(key), list):
                return body[key]
    raise HTTPException(502, f"Unexpected upstream response: {str(body)[:300]}")


def build_series(body, start: datetime, end: datetime) -> pd.Series:
    """API response -> regular 5-min series of InCount in naive local time; missing bins = 0."""
    rows = extract_rows(body)
    if not rows:
        raise HTTPException(404, "No visits data returned")
    df = pd.DataFrame(rows)
    if "Datetime" not in df.columns or "InCount" not in df.columns:
        raise HTTPException(
            502, f"Unexpected columns {list(df.columns)}; first row: {rows[0]}"
        )
    ts = pd.to_datetime(df["Datetime"], utc=True)
    if TIMESTAMPS_ARE_LOCAL:
        ts = ts.dt.tz_localize(None)                       # keep wall-clock as is
    else:
        ts = ts.dt.tz_convert(LOCAL_TZ).dt.tz_localize(None)
    s = pd.Series(df["InCount"].astype(float).values, index=pd.DatetimeIndex(ts))
    s = s.groupby(level=0).sum().sort_index()
    full = pd.date_range(start, end - timedelta(minutes=BIN_MINUTES),
                         freq=f"{BIN_MINUTES}min")
    return s.reindex(full, fill_value=0.0)


def compute_baselines(occupancy: pd.Series, percentile: float) -> dict:
    """Per-period baselines (+ 'global' fallback) from open, non-empty windows."""
    labels = period_labels(occupancy.index)
    mask = labels.notna() & (occupancy > 0)
    windows, win_labels = occupancy[mask], labels[mask]
    if windows.empty:
        raise HTTPException(404, "Not enough data to build a baseline")

    global_b = {
        "baseline": float(windows.quantile(percentile)),
        "max": float(windows.max()),
        "samples": int(len(windows)),
        "fallback": False,
    }
    baselines = {"global": global_b}
    for name in PERIODS:
        vals = windows[win_labels == name]
        if len(vals) >= MIN_SAMPLES:
            baselines[name] = {
                "baseline": float(vals.quantile(percentile)),
                "max": float(vals.max()),
                "samples": int(len(vals)),
                "fallback": False,
            }
        else:
            baselines[name] = {**global_b, "samples": int(len(vals)), "fallback": True}
    return baselines


def crowd_level(ratio: float) -> str:
    if ratio < 0.35:
        return "quiet"
    if ratio < 0.65:
        return "moderate"
    if ratio < 0.85:
        return "busy"
    return "crowded"


@router.get("/crowd")
async def get_crowd_endpoint(
    place_code: Optional[str] = Query("dining-auth"),
    stay_minutes: int = Query(20, ge=BIN_MINUTES),
    percentile: float = Query(0.95, gt=0, le=1),
):
    """Estimate how crowded a place is right now vs. its own history, per meal period."""
    now_local = datetime.now(LOCAL_TZ).replace(tzinfo=None)
    end = now_local.replace(minute=now_local.minute - now_local.minute % BIN_MINUTES,
                            second=0, microsecond=0)      # last complete bin boundary
    start = end - timedelta(days=HISTORY_DAYS)

    url = "https://app.product-me.eu/api/v1/clientApi/get-visits/getVisitsBy5Minutes"
    headers = {"x-api-key": f"{API_KEY}", "content-type": "application/json"}
    payload = {
        "storeCodes": [place_code],
        "from": to_api_time(start),
        "to": to_api_time(end),
        "splitByGender": False,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=headers, json=payload)
    if resp.status_code != 200:
        raise HTTPException(resp.status_code, "Upstream visits API error")

    series = build_series(resp.json(), start, end)

    n_bins = max(1, stay_minutes // BIN_MINUTES)
    occupancy = series.rolling(n_bins).sum().dropna()      # overlapping windows, stride = 1 bin

    baselines = compute_baselines(occupancy, percentile)

    last_ts = occupancy.index[-1]
    period = period_labels(occupancy.index[-1:]).iloc[0]
    result = {
        "place_code": place_code,
        "as_of": last_ts.isoformat(),                      # local time
        "window_minutes": stay_minutes,
        "period": period,
    }

    if period is None:                                     # currently closed
        return {**result, "is_open": False, "level": "closed",
                "current_window_visits": None, "baseline_visits": None, "ratio": None}

    b = {"baseline": max([b["baseline"] for b in baselines.values()])}
    current = float(occupancy.iloc[-1])
    ratio = current / b["baseline"] if b["baseline"] else 0.0
    return {
        **result,
        "is_open": True,
        "current_window_visits": current,
        "baseline_visits": b["baseline"],
        "ratio": round(ratio, 3),
        "level": crowd_level(ratio),
    }