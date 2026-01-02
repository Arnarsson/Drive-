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
    travel_mode = Column(String(20), default="DRIVE")  # DRIVE/WALK/BICYCLE/TRANSIT
    distance_km = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
