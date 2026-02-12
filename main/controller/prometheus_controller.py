from fastapi import APIRouter, Depends
from main.app.prometheus.generation import executeWorkflow
from main.app.prometheus.util import verifyAPIKey
import time

router = APIRouter(
    prefix="/rag",
    tags=["Prometheus"]
)

@router.get("/health")
async def health():
    return {"status": "ok", "service": "prometheus"}

@router.get("/key")
async def apiKeyTest(api_key: str = Depends(verifyAPIKey)):
    return {"message": "API", "secured": True}

@router.get("/")
async def rag(text: str, api_key: str = Depends(verifyAPIKey)):
    try:
        response = executeWorkflow(text)
        return {"success": True, "response": response, "timestamp": str(time.time())}
    except Exception as e:
        return {"success": False, "error": str(e), "timestamp": str(time.time())}