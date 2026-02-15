from fastapi import APIRouter, Response, Depends, Body, HTTPException

from main.app.auth.auth import *

router = APIRouter(
    prefix="/auth",
    tags=["Auth"]
)

@router.get("/health")
def health():
    return {"status": "ok", "service": "auth"}

@router.post("/register")
def register(username: str = Body(...), email: str = Body(...), password: str = Body(...)):
    try:
        result = createUserAccount(username, email, password)
        return {"message": "success", "user": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/login")
def login(response: Response, username: str = Body(...), password: str = Body(...)):
    user = authenticateUser(username, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    accessToken = createAccessToken(data={"userId": str(user["userId"]), "level": user["accessLevel"]})
    
    response.set_cookie(
        key="mansa_token",
        value=accessToken,
        httponly=True,
        secure=True,
        samesite="lax"
    )

    return {
        "accessToken": accessToken,
        "tokenType": "bearer",
        "user": user
    }

@router.get("/me")
async def getMe(user: dict = Depends(getCurrentUser)):
    return {
        "status": "success",
        "user": user
    }
