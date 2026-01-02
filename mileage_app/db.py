import os
from datetime import datetime, date
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean, Date, DateTime
)
from sqlalchemy.orm import declarative_base, sessionmaker

# Support Vercel Postgres (POSTGRES_URL) or custom DB_URL or SQLite fallback
DB_URL = os.getenv("POSTGRES_URL") or os.getenv("DB_URL", "sqlite:///./mileage.db")

# Vercel Postgres uses postgres:// but SQLAlchemy needs postgresql://
if DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace("postgres://", "postgresql://", 1)

# For serverless (Vercel), use in-memory SQLite if no DB configured
if os.getenv("VERCEL") and DB_URL.startswith("sqlite:///./"):
    DB_URL = "sqlite:///:memory:"

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


# Your frequent destinations from Koerselsgodtgoerelse.xlsx + Atlas Group
DEFAULT_LOCATIONS = [
    # Home
    {"name": "Hjem", "address": "Platanvej 7", "postal_code": "2791", "is_home": True},

    # Most frequent work destinations
    {"name": "elbiil.dk", "address": "Klausdalsbrovej 601", "postal_code": "2750", "is_home": False},
    {"name": "Smedeholm (Herlev)", "address": "Smedeholm 12", "postal_code": "2730", "is_home": False},
    {"name": "Talent Garden", "address": "Danneskiold-Samsøes Allé 41", "postal_code": "1434", "is_home": False},
    {"name": "FLEXeCHARGE", "address": "Rahbeks Allé 21", "postal_code": "1801", "is_home": False},
    {"name": "Bigum & Co", "address": "Rued Langgaards Vej 8", "postal_code": "2300", "is_home": False},
    {"name": "Kanalholmen", "address": "Kanalholmen 1", "postal_code": "2650", "is_home": False},
    {"name": "Højbro Plads", "address": "Højbro Plads 5-7", "postal_code": "1200", "is_home": False},
    {"name": "Erhvervshus Hovedstaden", "address": "Fruebjergvej 3", "postal_code": "2100", "is_home": False},

    # New: Atlas Group
    {"name": "Atlas Group", "address": "Store Kongensgade 81", "postal_code": "1264", "is_home": False},

    # Copenhagen locations
    {"name": "Fuglevangsvej", "address": "Fuglevangsvej 11", "postal_code": "1962", "is_home": False},
    {"name": "Nannasgade", "address": "Nannasgade 28", "postal_code": "2200", "is_home": False},
    {"name": "Islands Brygge", "address": "Islands Brygge 79b", "postal_code": "2300", "is_home": False},
    {"name": "Center Blvd", "address": "Center Blvd. 5", "postal_code": "2300", "is_home": False},
    {"name": "Frederiksborggade", "address": "Frederiksborggade 14", "postal_code": "1360", "is_home": False},
    {"name": "Birkedommervej", "address": "Birkedommervej 31", "postal_code": "2400", "is_home": False},
    {"name": "Bryghusgade", "address": "Bryghusgade 8", "postal_code": "1473", "is_home": False},
    {"name": "Admiralgade", "address": "Admiralgade 25", "postal_code": "1066", "is_home": False},
    {"name": "Overgaden", "address": "Overgaden Oven Vandet 90", "postal_code": "1415", "is_home": False},
    {"name": "Roskildevej", "address": "Roskildevej 46", "postal_code": "2000", "is_home": False},
    {"name": "IDA Conference", "address": "Kalvebod Brygge 31", "postal_code": "1560", "is_home": False},
    {"name": "DTU", "address": "Anker Engelunds Vej 1, Bygning 101A", "postal_code": "2800", "is_home": False},

    # Dragør area
    {"name": "Kirkevej (Dragør)", "address": "Kirkevej 7", "postal_code": "2791", "is_home": False},
    {"name": "Framehouse", "address": "A. P. Møllers Allé 43B", "postal_code": "2791", "is_home": False},

    # Other
    {"name": "Oscar Pettifords Vej", "address": "Oscar Pettifords Vej 15", "postal_code": "2450", "is_home": False},
    {"name": "Werner Valeur", "address": "Werner Valeur", "postal_code": "2840", "is_home": False},

    # Jylland
    {"name": "Kolding Storcenter", "address": "Kolding Storcenter", "postal_code": "6000", "is_home": False},
    {"name": "Vejen", "address": "Vejen Rådhusplads", "postal_code": "6600", "is_home": False},
    {"name": "Frederikshavn", "address": "Nordhavnsvej 1", "postal_code": "9900", "is_home": False},

    # Fyn
    {"name": "Faaborg", "address": "Faaborgvej 10", "postal_code": "5250", "is_home": False},
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
