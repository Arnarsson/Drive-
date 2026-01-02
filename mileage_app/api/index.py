import sys
import os

# Add mileage_app directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the FastAPI app - Vercel auto-detects 'app' variable
from app import app
