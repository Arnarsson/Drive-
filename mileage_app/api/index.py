from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()

@app.get("/")
def home():
    return HTMLResponse("<h1>Mileage App Works!</h1><p>Basic test successful.</p>")

@app.get("/api/health")
def health():
    return {"status": "ok"}
