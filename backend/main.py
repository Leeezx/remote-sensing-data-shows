from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import (
    health,
    irrigation,
    layers,
    query,
    regions,
    series,
    tiles,
)
from backend.runtime_config import CORS_ORIGINS, ENABLE_API_DOCS


def create_app(
    enable_api_docs: bool | None = None,
    cors_origins: tuple[str, ...] | None = None,
) -> FastAPI:
    docs_enabled = ENABLE_API_DOCS if enable_api_docs is None else enable_api_docs
    selected_origins = CORS_ORIGINS if cors_origins is None else cors_origins
    selected_origins = tuple(
        origin.strip() for origin in selected_origins if origin.strip()
    )

    application = FastAPI(
        title="Remote Sensing Data API",
        description="API for remote sensing data display and analysis",
        version="0.1.0",
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    if selected_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(selected_origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    application.include_router(health.router, prefix="/api")
    application.include_router(layers.router, prefix="/api")
    application.include_router(query.router, prefix="/api")
    application.include_router(series.router, prefix="/api")
    application.include_router(regions.router, prefix="/api")
    application.include_router(irrigation.router, prefix="/api")
    application.include_router(tiles.cog_tiler, prefix="/cog")
    application.include_router(tiles.router, prefix="/data")

    @application.get("/")
    def root():
        return {"message": "Remote Sensing Data API", "version": "0.1.0"}

    return application


app = create_app()
