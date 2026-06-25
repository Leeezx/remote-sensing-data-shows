from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import health

app = FastAPI(
    title="Remote Sensing Data API",
    description="API for remote sensing data display and analysis",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")


@app.get("/")
def root():
    return {"message": "Remote Sensing Data API", "version": "0.1.0"}
