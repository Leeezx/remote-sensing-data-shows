import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import health

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


@app.get("/")
def root():
    return {"message": "Remote Sensing Data API", "version": "0.1.0"}
