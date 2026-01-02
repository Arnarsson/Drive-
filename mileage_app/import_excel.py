#!/usr/bin/env python3
"""
Import historical trips from Koerselsgodtgoerelse.xlsx into the mileage app database.

Usage:
    python import_excel.py [--dry-run]
"""

import os
import sys
import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from db import init_db, SessionLocal, Trip, SavedLocation


def parse_date(val):
    """Parse various date formats from Excel."""
    if pd.isna(val):
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, str):
        val = val.strip()
        # Try common formats
        for fmt in ["%Y-%m-%d", "%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"]:
            try:
                return datetime.strptime(val, fmt).date()
            except ValueError:
                continue
    return None


def parse_km(val):
    """Parse kilometer value from Excel."""
    if pd.isna(val):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        # Handle Danish decimal (comma) and clean up
        val = val.replace(",", ".").replace(" ", "").strip()
        try:
            return float(val)
        except ValueError:
            return 0.0
    return 0.0


def import_excel(excel_path: str, dry_run: bool = False):
    """Import trips from Excel file."""
    print(f"Reading Excel file: {excel_path}")
    xl = pd.ExcelFile(excel_path)

    trips_to_import = []
    skipped = 0
    errors = []

    for sheet_name in xl.sheet_names:
        if "Kørselsgodtgørelse" not in sheet_name:
            continue

        print(f"\nProcessing: {sheet_name}")
        df = pd.read_excel(xl, sheet_name=sheet_name, header=None)

        # Data starts at row 17 (index 17)
        # Columns:
        #   1: Date
        #   2: Description
        #   3: Erhverv (1 = business)
        #   5: Fra (origin street)
        #   6: Fra postal code
        #   7: Til (destination street)
        #   8: Til postal code
        #   9: Fram km
        #  10: Tilbage km
        #  11: Total km (erhverv)

        for i in range(17, len(df)):
            try:
                row = df.iloc[i]

                # Parse date
                trip_date = parse_date(row[1])
                if not trip_date:
                    continue

                # Parse description/purpose
                purpose = str(row[2]).strip() if pd.notna(row[2]) else ""
                if not purpose or purpose == "nan":
                    continue

                # Parse origin
                fra_street = str(row[5]).strip() if pd.notna(row[5]) else ""
                fra_post = str(row[6]).split(".")[0].strip() if pd.notna(row[6]) else ""
                if not fra_street or fra_street == "nan":
                    continue

                # Parse destination
                til_street = str(row[7]).strip() if pd.notna(row[7]) else ""
                til_post = str(row[8]).split(".")[0].strip() if pd.notna(row[8]) else ""
                if not til_street or til_street == "nan":
                    continue
                if "Beregnes" in til_post:
                    continue

                # Parse distances
                km_frem = parse_km(row[9])
                km_tilbage = parse_km(row[10])
                km_total = parse_km(row[11])

                # Determine if round trip
                round_trip = km_tilbage > 0 and km_frem > 0

                # Calculate one-way distance
                if round_trip and km_total > 0:
                    one_way_km = km_total / 2
                elif km_frem > 0:
                    one_way_km = km_frem
                else:
                    one_way_km = km_total

                if km_total <= 0:
                    continue

                # Build origin/destination strings
                origin = f"{fra_street}, {fra_post}" if fra_post else fra_street
                destination = f"{til_street}, {til_post}" if til_post else til_street

                # Clean up strings
                origin = origin.replace("\n", " ").replace("\t", " ").strip()
                destination = destination.replace("\n", " ").replace("\t", " ").strip()
                purpose = purpose.replace("\n", " ").replace("\t", " ").strip()

                trips_to_import.append({
                    "trip_date": trip_date,
                    "purpose": purpose[:500],
                    "origin": origin[:500],
                    "destination": destination[:500],
                    "round_trip": round_trip,
                    "travel_mode": "DRIVE",
                    "distance_km": round(km_total, 1),
                    "distance_one_way_km": round(one_way_km, 1),
                })

            except Exception as e:
                errors.append(f"Row {i} in {sheet_name}: {e}")
                skipped += 1

    print(f"\n{'='*50}")
    print(f"Found {len(trips_to_import)} trips to import")
    print(f"Skipped {skipped} rows with errors")

    if errors[:5]:
        print("\nFirst 5 errors:")
        for e in errors[:5]:
            print(f"  - {e}")

    if dry_run:
        print("\n[DRY RUN] Would import the following trips:")
        for t in trips_to_import[:10]:
            print(f"  {t['trip_date']} | {t['purpose'][:30]} | {t['distance_km']} km")
        if len(trips_to_import) > 10:
            print(f"  ... and {len(trips_to_import) - 10} more")
        return

    # Initialize database and import
    print("\nInitializing database...")
    init_db()

    db = SessionLocal()
    try:
        imported = 0
        duplicates = 0

        for t in trips_to_import:
            # Check for duplicate (same date, origin, destination)
            existing = db.query(Trip).filter(
                Trip.trip_date == t["trip_date"],
                Trip.origin == t["origin"],
                Trip.destination == t["destination"]
            ).first()

            if existing:
                duplicates += 1
                continue

            trip = Trip(**t)
            db.add(trip)
            imported += 1

        db.commit()
        print(f"\n✅ Imported {imported} trips")
        print(f"⏭️  Skipped {duplicates} duplicates")

    except Exception as e:
        db.rollback()
        print(f"\n❌ Error importing: {e}")
        raise
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Import trips from Excel")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be imported")
    parser.add_argument("--excel", default="../Koerselsgodtgoerelse.xlsx", help="Path to Excel file")
    args = parser.parse_args()

    excel_path = Path(__file__).parent / args.excel
    if not excel_path.exists():
        print(f"Error: Excel file not found: {excel_path}")
        sys.exit(1)

    import_excel(str(excel_path), dry_run=args.dry_run)


if __name__ == "__main__":
    main()
