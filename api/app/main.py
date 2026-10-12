import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import (admin, apply, audits, auth, billing, dashboard, driverapply, gps,
                         employerreply, live, notifications, roadtestreply, rules, signing, trips,
                         uploading,
                         vault)

# TripProof's own log lines (mail sent / failed, billing…) go to the container log next to uvicorn's.
logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s: %(message)s")

app = FastAPI(title="TripProof API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (auth, vault, trips, dashboard, audits, rules, admin, notifications, apply, billing,
          driverapply, signing, uploading, employerreply, roadtestreply, live, gps):
    app.include_router(r.router)


@app.get("/api/health")
def health():
    return {"ok": True}
