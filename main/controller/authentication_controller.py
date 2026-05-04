from datetime import datetime, timedelta
from config import getSession
from main.utils.util import log, limiter, logError

from fastapi import APIRouter, Response, Body, HTTPException, Request, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from main.app.authentication.authentication import AuthenticationManager
from main.app.authentication.util import createAccessToken
from main.app.authentication.sso import getGoogleSSO
from main.app.authentication.constants import COOKIE_NAME, COOKIE_PATH, COOKIE_SAMESITE, TOKEN_EXPIRY_HOURS
from main.app.authentication.session import SessionManager

router = APIRouter(prefix="/auth", tags=["Authentication"])

def isSecureScheme(request: Request) -> bool:
    return request.url.scheme == "https" if request.url.scheme else False

@router.get("/health")
def health(request: Request):
    return {"status": "ok", "service": "authentication"}

@router.post("/register")
@limiter.limit("5/minute")
def register(
    request: Request,
    response: Response,
    username: str = Body(..., min_length=3, max_length=50),
    email: str = Body(..., min_length=5, max_length=100),
    password: str = Body(..., min_length=6, max_length=100),
    db: Session = Depends(getSession),
):
    try:
        AuthenticationManager.createUserAccount(db, username, email, password)

        user = AuthenticationManager.authenticateUser(db, username, password)
        if not user:
            raise HTTPException(status_code=401, detail="Auto-login failed after registration")

        userAgent = request.headers.get("User-Agent", "")
        expiresAt = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRY_HOURS)
        session = SessionManager.createSession(db, user["userId"], userAgent, request, expiresAt)

        accessToken, _ = createAccessToken(data={"userId": str(user["userId"]), "sessionId": str(session.sessionId)})
        useCookieSecure = isSecureScheme(request)
        response.set_cookie(
            key=COOKIE_NAME,
            value=accessToken,
            httponly=True,
            secure=useCookieSecure,
            samesite=COOKIE_SAMESITE,
            path=COOKIE_PATH,
        )

        return {"message": "success", "accessToken": accessToken, "tokenType": "bearer", "user": user}
    except HTTPException:
        raise
    except ValueError as e:
        logError("auth", f"Registration validation error: {str(e)}", e)
        raise HTTPException(status_code=400, detail="Registration failed. Invalid input.")
    except Exception as e:
        logError("auth", "Unexpected error during registration", e)
        raise HTTPException(status_code=500, detail="Registration failed. Internal error.")

@router.post("/login")
@limiter.limit("5/minute")
def login(
    request: Request,
    response: Response,
    username: str = Body(..., min_length=3, max_length=50),
    password: str = Body(..., min_length=1),
    db: Session = Depends(getSession),
):
    user = AuthenticationManager.authenticateUser(db, username, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    userAgent = request.headers.get("User-Agent", "")
    expiresAt = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRY_HOURS)
    session = SessionManager.createSession(db, user["userId"], userAgent, request, expiresAt)

    accessToken, _ = createAccessToken(data={"userId": str(user["userId"]), "sessionId": str(session.sessionId)})
    useCookieSecure = isSecureScheme(request)
    response.set_cookie(
        key=COOKIE_NAME,
        value=accessToken,
        httponly=True,
        secure=useCookieSecure,
        samesite=COOKIE_SAMESITE,
        path=COOKIE_PATH,
    )

    return {"accessToken": accessToken, "tokenType": "bearer", "user": user}

@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(getSession)):
    from main.app.authentication.util import verifyAccessToken

    token = request.headers.get("X-Access-Token")
    if not token:
        authHeader = request.headers.get("Authorization")
        if authHeader and authHeader.startswith("Bearer "):
            token = authHeader.split(" ")[1]

    if token:
        try:
            payload = verifyAccessToken(token)
            userId = payload.get("userId")
            sessionId = payload.get("sessionId")
            if userId and sessionId:
                try:
                    sessionId = int(sessionId)
                    SessionManager.revokeSession(db, sessionId, userId)
                except (ValueError, TypeError):
                    pass
        except Exception:
            pass

    useCookieSecure = isSecureScheme(request)
    response.delete_cookie(
        key=COOKIE_NAME, httponly=True, secure=useCookieSecure, samesite=COOKIE_SAMESITE, path=COOKIE_PATH
    )
    return {"message": "Successfully logged out"}

@router.get("/google")
@limiter.limit("5/minute")
async def googleLogin(request: Request):
    log("auth", "Google Login")

    redirectUrl = request.query_params.get("redirect_url", "")
    if not redirectUrl:
        redirectUrl = request.headers.get("referer", "")

    log("auth", f"Redirect URL: {redirectUrl}")

    googleSSO = getGoogleSSO()
    async with googleSSO:
        return await googleSSO.get_login_redirect(state=redirectUrl)

@router.get("/callback")
@limiter.limit("5/minute")
async def googleCallback(request: Request, response: Response, state: str = None, db: Session = Depends(getSession)):
    log("auth", "--- Google Callback Start ---")
    log("auth", f"State parameter: {state}")

    googleSSO = getGoogleSSO()

    try:
        async with googleSSO:
            userInfo = await googleSSO.verify_and_process(request)

        if not userInfo:
            raise HTTPException(status_code=400, detail="No user info received from Google")

        googleId = userInfo.id
        email = userInfo.email

        log("auth", f"User identified: {email}")
        user = AuthenticationManager.authenticateGoogleUser(db, googleId)

        if not user:
            log("auth", "New user detected, creating account...")
            username = email.split("@")[0]
            AuthenticationManager.createUserAccount(db, username=username, email=email, googleId=googleId)
            user = AuthenticationManager.authenticateGoogleUser(db, googleId)

        userAgent = request.headers.get("User-Agent", "")
        expiresAt = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRY_HOURS)
        session = SessionManager.createSession(db, user["userId"], userAgent, request, expiresAt)

        accessToken, _ = createAccessToken(data={"userId": str(user["userId"]), "sessionId": str(session.sessionId)})
        isSecure = isSecureScheme(request)

        response.set_cookie(
            key=COOKIE_NAME, value=accessToken, httponly=True, secure=isSecure, samesite="none", path="/"
        )

        if state:
            response = RedirectResponse(url=f"{state}?token={accessToken}")
            response.set_cookie(
                key=COOKIE_NAME, value=accessToken, httponly=True, secure=isSecure, samesite="none", path="/"
            )
            return response

        log("auth", "--- Google Callback End ---")
        return {"accessToken": accessToken, "tokenType": "bearer", "user": user}

    except HTTPException:
        raise
    except Exception as e:
        logError("auth", f"Critical error in Google callback: {str(e)}", e)
        raise HTTPException(status_code=500, detail="Internal server error during Google login")