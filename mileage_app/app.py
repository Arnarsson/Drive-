import os
import csv
import io
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

from db import init_db, get_db, seed_locations, Trip, SavedLocation

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

# Danish SKAT kørselsgodtgørelse rates by year
# Source: https://skat.dk - rates for tax-free mileage reimbursement
DK_RATES = {
    2023: {"high": 3.73, "low": 2.19, "threshold": 20000},
    2024: {"high": 3.79, "low": 2.23, "threshold": 20000},
    2025: {"high": 3.94, "low": 2.28, "threshold": 20000},
    2026: {"high": 3.94, "low": 2.28, "threshold": 20000},  # Placeholder
}

# ---------- FastAPI ----------
app = FastAPI(title="Kørselsgodtgørelse App")

# Use absolute paths for Vercel serverless
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Only mount static files if not on Vercel (Vercel serves them separately)
if not os.getenv("VERCEL"):
    app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


# ---------- Pydantic models ----------
class TripCreate(BaseModel):
    trip_date: date
    purpose: str = Field(min_length=2, max_length=500)
    origin: str = Field(min_length=2, max_length=500)
    destination: str = Field(min_length=2, max_length=500)
    round_trip: bool = True  # Default to round trip (most common for business)
    travel_mode: str = "DRIVE"


class TripOut(BaseModel):
    id: int
    trip_date: date
    purpose: str
    origin: str
    destination: str
    round_trip: bool
    travel_mode: str
    distance_km: float
    distance_one_way_km: Optional[float] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TripUpdate(BaseModel):
    """Partial update for a trip - only provided fields will be updated."""
    trip_date: Optional[date] = None
    purpose: Optional[str] = Field(default=None, min_length=2, max_length=500)


class DistancePreview(BaseModel):
    """Request for distance preview."""
    origin: str = Field(min_length=2, max_length=500)
    destination: str = Field(min_length=2, max_length=500)
    round_trip: bool = True
    travel_mode: str = "DRIVE"


class DistancePreviewOut(BaseModel):
    """Response for distance preview."""
    one_way_km: float
    total_km: float
    round_trip: bool


class LocationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    address: str = Field(min_length=2, max_length=500)
    postal_code: Optional[str] = None
    is_home: bool = False


class LocationOut(BaseModel):
    id: int
    name: str
    address: str
    postal_code: Optional[str]
    is_home: bool
    usage_count: int

    class Config:
        from_attributes = True


class SummaryOut(BaseModel):
    year: int
    trip_count: int
    total_km: float
    reimbursement_dkk: float
    rate_high: float
    rate_low: float


# ---------- Google Routes API call ----------
async def compute_distance_km(
    origin: str,
    destination: str,
    travel_mode: str = "DRIVE",
    region_code: str = "DK",
) -> float:
    """Compute distance via Google Routes API. Returns one-way distance in km."""
    if not GOOGLE_MAPS_API_KEY:
        raise HTTPException(status_code=500, detail="Missing GOOGLE_MAPS_API_KEY")

    travel_mode = travel_mode.upper().strip()
    if travel_mode not in {"DRIVE", "WALK", "BICYCLE", "TRANSIT"}:
        raise HTTPException(status_code=400, detail="Invalid travel_mode")

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": "routes.distanceMeters,routes.duration",
    }

    payload = {
        "origin": {"address": origin},
        "destination": {"address": destination},
        "travelMode": travel_mode,
        "units": "METRIC",
        "languageCode": "da-DK",
        "regionCode": region_code,
        "routingPreference": "TRAFFIC_UNAWARE",
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(ROUTES_ENDPOINT, headers=headers, json=payload)
    except httpx.RequestError as e:
        logger.exception("Routes API request failed")
        raise HTTPException(status_code=502, detail=f"Routes API error: {e}") from e

    if resp.status_code != 200:
        logger.error("Routes API error %s: %s", resp.status_code, resp.text[:500])
        raise HTTPException(status_code=502, detail=f"Routes API error {resp.status_code}")

    data = resp.json()
    routes = data.get("routes", [])
    if not routes:
        raise HTTPException(status_code=502, detail="No routes found")

    distance_m = routes[0].get("distanceMeters")
    if distance_m is None:
        raise HTTPException(status_code=502, detail="Missing distance in response")

    return float(distance_m) / 1000.0


def dk_reimbursement(total_km: float, year: int) -> float:
    """Calculate Danish tax-free mileage reimbursement for a given year."""
    rates = DK_RATES.get(year, DK_RATES[2026])
    threshold = rates["threshold"]
    if total_km <= threshold:
        return total_km * rates["high"]
    return (threshold * rates["high"]) + ((total_km - threshold) * rates["low"])


# ---------- UI ----------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ---------- Locations API ----------
@app.get("/api/locations", response_model=List[LocationOut])
def list_locations(db: Session = Depends(get_db)):
    """List all saved locations, sorted by home first, then usage count."""
    return (
        db.query(SavedLocation)
        .order_by(SavedLocation.is_home.desc(), SavedLocation.usage_count.desc())
        .all()
    )


@app.post("/api/locations", response_model=LocationOut)
def create_location(payload: LocationCreate, db: Session = Depends(get_db)):
    loc = SavedLocation(**payload.model_dump())
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return loc


@app.delete("/api/locations/{location_id}")
def delete_location(location_id: int, db: Session = Depends(get_db)):
    loc = db.query(SavedLocation).filter(SavedLocation.id == location_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")
    db.delete(loc)
    db.commit()
    return {"ok": True}


# ---------- Trips API ----------
@app.get("/api/trips", response_model=List[TripOut])
def list_trips(year: Optional[int] = Query(default=None), db: Session = Depends(get_db)):
    q = db.query(Trip).order_by(Trip.trip_date.desc(), Trip.id.desc())
    if year:
        q = q.filter(Trip.trip_date >= date(year, 1, 1), Trip.trip_date <= date(year, 12, 31))
    return q.all()


@app.post("/api/trips", response_model=TripOut)
async def create_trip(payload: TripCreate, db: Session = Depends(get_db)):
    # Compute one-way distance
    one_way_km = await compute_distance_km(
        origin=payload.origin,
        destination=payload.destination,
        travel_mode=payload.travel_mode,
        region_code=DEFAULT_REGION_CODE,
    )

    # Total distance (round trip doubles it)
    total_km = one_way_km * 2 if payload.round_trip else one_way_km

    trip = Trip(
        trip_date=payload.trip_date,
        purpose=payload.purpose,
        origin=payload.origin,
        destination=payload.destination,
        round_trip=payload.round_trip,
        travel_mode=payload.travel_mode.upper(),
        distance_km=round(total_km, 1),
        distance_one_way_km=round(one_way_km, 1),
    )
    db.add(trip)

    # Update usage count for matching saved locations
    for loc in db.query(SavedLocation).all():
        full_addr = f"{loc.address}, {loc.postal_code}" if loc.postal_code else loc.address
        if full_addr in payload.origin or full_addr in payload.destination:
            loc.usage_count += 1

    db.commit()
    db.refresh(trip)
    return trip


@app.delete("/api/trips/{trip_id}")
def delete_trip(trip_id: int, db: Session = Depends(get_db)):
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    db.delete(trip)
    db.commit()
    return {"ok": True}


@app.patch("/api/trips/{trip_id}", response_model=TripOut)
def update_trip(trip_id: int, payload: TripUpdate, db: Session = Depends(get_db)):
    """Partial update of a trip (date and purpose only - distance cannot be changed)."""
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    # Only update provided fields
    if payload.trip_date is not None:
        trip.trip_date = payload.trip_date
    if payload.purpose is not None:
        trip.purpose = payload.purpose

    db.commit()
    db.refresh(trip)
    return trip


@app.post("/api/preview-distance", response_model=DistancePreviewOut)
async def preview_distance(payload: DistancePreview):
    """Preview distance calculation without saving a trip."""
    one_way_km = await compute_distance_km(
        origin=payload.origin,
        destination=payload.destination,
        travel_mode=payload.travel_mode,
        region_code=DEFAULT_REGION_CODE,
    )

    total_km = one_way_km * 2 if payload.round_trip else one_way_km

    return DistancePreviewOut(
        one_way_km=round(one_way_km, 1),
        total_km=round(total_km, 1),
        round_trip=payload.round_trip,
    )


@app.get("/api/summary", response_model=SummaryOut)
def summary(year: int = Query(...), db: Session = Depends(get_db)):
    trips = (
        db.query(Trip)
        .filter(Trip.trip_date >= date(year, 1, 1), Trip.trip_date <= date(year, 12, 31))
        .all()
    )
    total_km = round(sum(t.distance_km for t in trips), 1)
    rates = DK_RATES.get(year, DK_RATES[2026])

    return SummaryOut(
        year=year,
        trip_count=len(trips),
        total_km=total_km,
        reimbursement_dkk=round(dk_reimbursement(total_km, year), 2),
        rate_high=rates["high"],
        rate_low=rates["low"],
    )


@app.get("/api/export.csv")
def export_csv(year: int = Query(...), db: Session = Depends(get_db)):
    """Export trips in CSV format compatible with Danish tax documentation."""
    trips = (
        db.query(Trip)
        .filter(Trip.trip_date >= date(year, 1, 1), Trip.trip_date <= date(year, 12, 31))
        .order_by(Trip.trip_date.asc(), Trip.id.asc())
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")  # Danish Excel uses semicolon

    # Header matching Dinero template structure
    writer.writerow([
        "Dato", "Beskrivelse", "Erhverv", "Fra", "Til",
        "Frem (km)", "Tilbage (km)", "Total (km)"
    ])

    for t in trips:
        one_way = t.distance_one_way_km or (t.distance_km / 2 if t.round_trip else t.distance_km)
        writer.writerow([
            t.trip_date.strftime("%Y-%m-%d"),
            t.purpose,
            "1",  # Erhverv = business
            t.origin,
            t.destination,
            f"{one_way:.1f}".replace(".", ","),  # Danish decimal
            f"{one_way:.1f}".replace(".", ",") if t.round_trip else "0",
            f"{t.distance_km:.1f}".replace(".", ","),
        ])

    output.seek(0)
    filename = f"koerselsgodtgoerelse_{year}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class CalendarEvent(BaseModel):
    """Calendar event with location for trip suggestions."""
    date: str
    title: str
    location: str


@app.get("/api/calendar/events", response_model=List[CalendarEvent])
async def get_calendar_events():
    """
    Get upcoming calendar events with locations.
    Requires Google Calendar API credentials to be configured.
    """
    # Check if calendar is configured
    calendar_credentials = os.getenv("GOOGLE_CALENDAR_CREDENTIALS")
    if not calendar_credentials:
        raise HTTPException(
            status_code=501,
            detail="Calendar integration not configured. Set GOOGLE_CALENDAR_CREDENTIALS in .env"
        )

    # TODO: Implement Google Calendar API integration
    # For now, return sample data for development/testing
    # In production, this would fetch real calendar events
    sample_events = [
        {"date": "2025-01-15", "title": "Kundemøde hos TechCorp", "location": "Lyngby Hovedgade 72, 2800 Kgs. Lyngby"},
        {"date": "2025-01-18", "title": "Workshop hos Microsoft", "location": "Kanalvej 7, 2800 Kgs. Lyngby"},
        {"date": "2025-01-22", "title": "Salgsmøde", "location": "Vesterbrogade 1, 1620 København V"},
    ]

    return sample_events


@app.on_event("startup")
def on_startup():
    try:
        init_db()
        # Seed saved locations from your Excel history
        db = next(get_db())
        seed_locations(db)
        logger.info("DB initialized with saved locations from your history.")
    except Exception as e:
        logger.error(f"Startup error (non-fatal on serverless): {e}")
