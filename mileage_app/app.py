import os
import csv
import logging
from datetime import date, datetime
from typing import Optional, List

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import init_db, get_db, Trip

load_dotenv()

# ---------- logging ----------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("mileage_app")

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
DEFAULT_REGION_CODE = os.getenv("DEFAULT_REGION_CODE", "DK")

ROUTES_ENDPOINT = "https://routes.googleapis.com/directions/v2:computeRoutes"

# ---------- FastAPI ----------
app = FastAPI(title="Mileage App (Routes API)")

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# ---------- Pydantic models ----------
class TripCreate(BaseModel):
    trip_date: date
    purpose: str = Field(min_length=2, max_length=500)
    origin: str = Field(min_length=2, max_length=500)
    destination: str = Field(min_length=2, max_length=500)
    round_trip: bool = False
    travel_mode: str = "DRIVE"  # DRIVE/WALK/BICYCLE/TRANSIT

class TripOut(BaseModel):
    id: int
    trip_date: date
    purpose: str
    origin: str
    destination: str
    round_trip: bool
    travel_mode: str
    distance_km: float
    created_at: datetime

    class Config:
        from_attributes = True

class SummaryOut(BaseModel):
    year: int
    trip_count: int
    total_km: float
    # Optional DK reimbursement estimate (simple model)
    reimbursement_estimate_dkk: Optional[float] = None

# ---------- Google Routes API call ----------
async def compute_distance_km(origin: str, destination: str, travel_mode: str = "DRIVE", region_code: str = "DK") -> float:
    """
    Uses Routes API computeRoutes and returns distance in km.
    Routes API supports address strings directly in waypoints.
    """
    if not GOOGLE_MAPS_API_KEY:
        raise HTTPException(status_code=500, detail="Missing GOOGLE_MAPS_API_KEY in environment.")

    travel_mode = travel_mode.upper().strip()
    if travel_mode not in {"DRIVE", "WALK", "BICYCLE", "TRANSIT"}:
        raise HTTPException(status_code=400, detail="travel_mode must be DRIVE, WALK, BICYCLE, or TRANSIT.")

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        # Field mask to return only what we need (distanceMeters + duration)
        # Google recommends field masks for efficiency.
        "X-Goog-FieldMask": "routes.distanceMeters,routes.duration",
    }

    payload = {
        "origin": {"address": origin},
        "destination": {"address": destination},
        "travelMode": travel_mode,
        "units": "METRIC",
        "languageCode": "en-US",
        # Bias address geocoding to Denmark when ambiguous
        "regionCode": region_code,
        # For taxes you usually want a stable distance (not traffic-time optimization)
        "routingPreference": "TRAFFIC_UNAWARE",
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(ROUTES_ENDPOINT, headers=headers, json=payload)
    except httpx.RequestError as e:
        logger.exception("Routes API request failed")
        raise HTTPException(status_code=502, detail=f"Routes API request error: {e}") from e

    if resp.status_code != 200:
        # Avoid leaking key; return useful info
        logger.error("Routes API error %s: %s", resp.status_code, resp.text[:500])
        raise HTTPException(status_code=502, detail=f"Routes API error {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    routes = data.get("routes", [])
    if not routes:
        raise HTTPException(status_code=502, detail="Routes API returned no routes.")
    distance_m = routes[0].get("distanceMeters")
    if distance_m is None:
        raise HTTPException(status_code=502, detail="Routes API response missing distanceMeters.")
    return float(distance_m) / 1000.0

# ---------- UI ----------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# ---------- API ----------
@app.get("/api/trips", response_model=List[TripOut])
def list_trips(
    year: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
):
    q = db.query(Trip).order_by(Trip.trip_date.desc(), Trip.id.desc())
    if year:
        q = q.filter(Trip.trip_date >= date(year, 1, 1), Trip.trip_date <= date(year, 12, 31))
    return q.all()

@app.post("/api/trips", response_model=TripOut)
async def create_trip(payload: TripCreate, db: Session = Depends(get_db)):
    km = await compute_distance_km(
        origin=payload.origin,
        destination=payload.destination,
        travel_mode=payload.travel_mode,
        region_code=DEFAULT_REGION_CODE,
    )
    if payload.round_trip:
        km *= 2.0

    trip = Trip(
        trip_date=payload.trip_date,
        purpose=payload.purpose,
        origin=payload.origin,
        destination=payload.destination,
        round_trip=payload.round_trip,
        travel_mode=payload.travel_mode.upper(),
        distance_km=round(km, 3),
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip

@app.delete("/api/trips/{trip_id}")
def delete_trip(trip_id: int, db: Session = Depends(get_db)):
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found.")
    db.delete(trip)
    db.commit()
    return {"ok": True}

def dk_reimbursement_estimate(total_km: float) -> float:
    """
    Simple estimate using common 2026 rates (up to 20,000 km and above).
    Verify your applicable year/rules.
    """
    rate_low = 3.94
    rate_high = 2.28
    threshold = 20000.0
    low_km = min(total_km, threshold)
    high_km = max(0.0, total_km - threshold)
    return (low_km * rate_low) + (high_km * rate_high)

@app.get("/api/summary", response_model=SummaryOut)
def summary(year: int = Query(...), db: Session = Depends(get_db)):
    trips = (
        db.query(Trip)
        .filter(Trip.trip_date >= date(year, 1, 1), Trip.trip_date <= date(year, 12, 31))
        .all()
    )
    total_km = round(sum(t.distance_km for t in trips), 3)
    return SummaryOut(
        year=year,
        trip_count=len(trips),
        total_km=total_km,
        reimbursement_estimate_dkk=round(dk_reimbursement_estimate(total_km), 2),
    )

@app.get("/api/export.csv")
def export_csv(year: int = Query(...), db: Session = Depends(get_db)):
    trips = (
        db.query(Trip)
        .filter(Trip.trip_date >= date(year, 1, 1), Trip.trip_date <= date(year, 12, 31))
        .order_by(Trip.trip_date.asc(), Trip.id.asc())
        .all()
    )

    def iter_csv():
        output = csv.StringIO()
        writer = csv.writer(output)
        writer.writerow(["date", "purpose", "origin", "destination", "round_trip", "mode", "distance_km"])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        for t in trips:
            writer.writerow([t.trip_date.isoformat(), t.purpose, t.origin, t.destination, t.round_trip, t.travel_mode, f"{t.distance_km:.3f}"])
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    filename = f"mileage_{year}.csv"
    return StreamingResponse(
        iter_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@app.on_event("startup")
def on_startup():
    init_db()
    logger.info("DB initialized and app started.")
