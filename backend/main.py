import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import (
    auth,
    export,
    health,
    irrigation,
    layers,
    query,
    regions,
    series,
    tiles,
)

load_dotenv()

app = FastAPI(
    title="Remote Sensing Data API",
    description="API for remote sensing data display and analysis",
    version="0.1.0",
)

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api/auth")
app.include_router(layers.router, prefix="/api")
app.include_router(query.router, prefix="/api")
app.include_router(series.router, prefix="/api")
app.include_router(regions.router, prefix="/api")
app.include_router(export.router, prefix="/api")
app.include_router(irrigation.router, prefix="/api")
# TiTiler dynamic COG tile endpoints (for SSM layer)
app.include_router(tiles.cog_tiler, prefix="/cog")
# Legacy static tile endpoints (for pre-generated PNG tiles of other layers)
app.include_router(tiles.router, prefix="/data")


@app.get("/")
def root():
    return {"message": "Remote Sensing Data API", "version": "0.1.0"}
