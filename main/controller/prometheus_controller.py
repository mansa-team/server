from main.utils.util import limiter

from fastapi import APIRouter, Depends, Request
import time

from main.app.prometheus.generation import PrometheusGenerator
from main.app.prometheus.util import verifyAPIKey

router = APIRouter(
    prefix="/prometheus",
    tags=["Prometheus"]
)

@router.get("/health")
def health():
    return {"status": "ok", "service": "prometheus"}

@router.get("/key")
def apiKeyTest(apiKey: str = Depends(verifyAPIKey)):
    return {"message": "API", "secured": True}

@router.get("/")
@limiter.limit("5/minute")
def generation(request: Request, text: str, apiKey: str = Depends(verifyAPIKey)):
    try:
        response = PrometheusGenerator().executeWorkflow(text)
        return {"success": True, "response": response, "timestamp": str(time.time())}
    except Exception as e:
        return {"success": False, "error": str(e), "timestamp": str(time.time())}