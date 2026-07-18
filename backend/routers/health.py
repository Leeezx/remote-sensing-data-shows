from fastapi import APIRouter, Response, status

from backend.readiness import collect_readiness_failures

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check():
    return {"status": "ok", "message": "Service is healthy"}


@router.get("/ready")
def readiness_check(response: Response):
    failures = collect_readiness_failures()
    if failures:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "dependencies": failures}
    return {"status": "ready", "dependencies": []}
