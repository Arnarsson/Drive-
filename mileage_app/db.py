import os
from datetime import datetime, date
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean, Date, DateTime
)
from sqlalchemy.orm import declarative_base, sessionmaker

DB_URL = os.getenv("DB_URL", "sqlite:///./mileage.db")

engine = create_engine(DB_URL, connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class Trip(Base):
    __tablename__ = "trips"

    id = Column(Integer, primary_key=True, index=True)
    trip_date = Column(Date, nullable=False, index=True)
    purpose = Column(String(500), nullable=False)
    origin = Column(String(500), nullable=False)
    destination = Column(String(500), nullable=False)
    round_trip = Column(Boolean, default=False)
    travel_mode = Column(String(20), default="DRIVE")
    distance_km = Column(Float, nullable=False)
    # Store one-way distance separately for Danish tax reporting (Frem/Tilbage)
    distance_one_way_km = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class SavedLocation(Base):
    """Saved locations for quick selection - seeded from your Excel history."""
    __tablename__ = "saved_locations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)  # Short name like "elbiil.dk" or "Talent Garden"
    address = Column(String(500), nullable=False)  # Full address
    postal_code = Column(String(10), nullable=True)
    is_home = Column(Boolean, default=False)  # Mark home/default origin
    usage_count = Column(Integer, default=0)  # Track frequency for sorting
    created_at = Column(DateTime, default=datetime.utcnow)


# Your frequent destinations from Koerselsgodtgoerelse.xlsx
DEFAULT_LOCATIONS = [
    {"name": "Hjem", "address": "Platanvej 7", "postal_code": "2791", "is_home": True},
    {"name": "elbiil.dk", "address": "Klausdalsbrovej 601", "postal_code": "2750", "is_home": False},
    {"name": "Smedeholm (Herlev)", "address": "Smedeholm 12", "postal_code": "2730", "is_home": False},
    {"name": "Talent Garden", "address": "Danneskiold-Samsøes Allé 41", "postal_code": "1434", "is_home": False},
    {"name": "Bigum & Co", "address": "Rued Langgaards Vej 8", "postal_code": "2300", "is_home": False},
    {"name": "FLEXeCHARGE", "address": "Rahbeks Alle 21", "postal_code": "1801", "is_home": False},
    {"name": "Kanalholmen", "address": "Kanalholmen 1", "postal_code": "2650", "is_home": False},
    {"name": "Højbro Plads", "address": "Højbro Plads 5-7", "postal_code": "1200", "is_home": False},
    {"name": "Erhvervshus Hovedstaden", "address": "Fruebjergvej 3", "postal_code": "2100", "is_home": False},
]


def init_db():
    Base.metadata.create_all(bind=engine)


def seed_locations(db):
    """Seed default locations if table is empty."""
    if db.query(SavedLocation).count() == 0:
        for loc in DEFAULT_LOCATIONS:
            db.add(SavedLocation(**loc))
        db.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
