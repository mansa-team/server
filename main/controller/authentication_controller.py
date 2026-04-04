from config import Config, getSession
from main.utils.util import log, limiter

from fastapi import APIRouter, Response, Body, HTTPException, Request, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
import traceback

from main.app.authentication.authentication import authManager
from main.app.authentication.util import *
from main.app.authentication.sso import getGoogleSSO

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

@router.get("/health")
def health(request: Request):
    return {"status": "ok", "service": "authenticaton"}

@router.post("/register")
@limiter.limit("5/minute")
def register(request: Request, response: Response, username: str = Body(...), email: str = Body(...), password: str = Body(...), db: Session = Depends(getSession)):
    try:
        authManager.createUserAccount(db, username, email, password)

        user = authManager.authenticateUser(db, username, password)
        if not user:
            raise HTTPException(status_code=401, detail="Auto-login failed after registration")
            
        accessToken = createAccessToken(data={"userId": str(user["userId"])})
        
        useCookieSecure = request.url.scheme == "https" if request.url.scheme else False
        
        response.set_cookie(
            key="mansa_token",
            value=accessToken,
            httponly=True,
            secure=useCookieSecure,
            samesite="lax"
        )
        
        return {
            "message": "success",
            "accessToken": accessToken,
            "tokenType": "bearer",
            "user": user
        }
    except HTTPException as e:
        raise e
    except Exception:
        raise HTTPException(status_code=400, detail="Registration failed. Internal error or credentials already in use.")

@router.post("/login")
@limiter.limit("5/minute")
def login(request: Request, response: Response, username: str = Body(...), password: str = Body(...), db: Session = Depends(getSession)):
    user = authManager.authenticateUser(db, username, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    accessToken = createAccessToken(data={"userId": str(user["userId"])})
    useCookieSecure = request.url.scheme == "https" if request.url.scheme else False
    response.set_cookie(
        key="mansa_token",
        value=accessToken,
        httponly=True,
        secure=useCookieSecure,
        samesite="lax"
    )

    return {
        "accessToken": accessToken,
        "tokenType": "bearer",
        "user": user
    }

@router.post("/logout")
def logout(response: Response):
    useCookieSecure = request.url.scheme == "https" if request.url.scheme else False
    response.delete_cookie(
        key="mansa_token",
        httponly=True,
        secure=useCookieSecure,
        samesite="lax",
        path="/"
    )
    return {"message": "Successfully logged out"}

@router.get("/google")
@limiter.limit("5/minute")
async def googleLogin(request: Request):
    log("auth", "Google Login")
    
    redirectUrl = request.query_params.get("redirect_url", "")
    if not redirectUrl:
        redirectUrl = request.headers.get("referer", "")
    
    log(f"auth", f"Redirect URL: {redirectUrl}")
    
    googleSSO = getGoogleSSO()
    async with googleSSO:
        return await googleSSO.get_login_redirect(state=redirectUrl)

@router.get("/callback")
@limiter.limit("5/minute")
async def googleCallback(request: Request, response: Response, state: str = None, db: Session = Depends(getSession)):
    log("auth", "--- Google Callback Start ---")
    log(f"auth", f"State parameter: {state}")
    
    googleSSO = getGoogleSSO()
    
    try:
        async with googleSSO:
            userInfo = await googleSSO.verify_and_process(request)
        
        if not userInfo:
            raise HTTPException(status_code=400, detail="No user info received from Google")
        
        googleId = userInfo.id
        email = userInfo.email
        
        log(f"auth", f"User identified: {email}")
        user = authManager.authenticateGoogleUser(db, googleId)
        
        if not user:
            log("auth", "New user detected, creating account...")
            username = email.split('@')[0]
            authManager.createUserAccount(db, username=username, email=email, googleId=googleId)
            user = authManager.authenticateGoogleUser(db, googleId)

        accessToken = createAccessToken(data={"userId": str(user["userId"])})
        
        frontendUrl = state if state else ""
        isSecure = frontendUrl.startswith("https") if frontendUrl else False
        separator = "&" if "?" in frontendUrl else "?"

        response = RedirectResponse(url=f"{frontendUrl}{separator}token={accessToken}")
        
        response.set_cookie(
            key="mansa_token",
            value=accessToken,
            httponly=True,
            secure=isSecure, 
            samesite="none",
            path="/" 
        )

        log("auth", f"SUCCESS: Redirecting to {frontendUrl}")
        log("auth", "--- Google Callback End ---")
        return response

    except Exception as e:
        log("auth", f"CRITICAL ERROR in callback: {str(e)}")
        log("auth", f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Internal server error during Google login")