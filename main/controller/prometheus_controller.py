from fastapi import APIRouter, Depends
import time

from main.app.prometheus.generation import executeWorkflow
from main.app.prometheus.util import verifyAPIKey

router = APIRouter(
    prefix="/prometheus",
    tags=["Prometheus"]
)

@router.get("/health")
def health():
    return {"status": "ok", "service": "prometheus"}

@router.get("/key")
def apiKeyTest(api_key: str = Depends(verifyAPIKey)):
    return {"message": "API", "secured": True}

@router.get("/")
def rag(text: str, api_key: str = Depends(verifyAPIKey)):
    try:
        response = executeWorkflow(text)
        return {"success": True, "response": response, "timestamp": str(time.time())}
    except Exception as e:
        return {"success": False, "error": str(e), "timestamp": str(time.time())}