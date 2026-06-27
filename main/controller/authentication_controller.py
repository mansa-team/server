import logging
from datetime import datetime, timedelta, timezone
from config import getSession
from main.utils.logging_config import limiter

from fastapi import APIRouter, Response, HTTPException, Request, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from main.app.authentication.authentication import AuthenticationManager
from main.app.authentication.util import createAccessToken, verifyAccessToken
from main.app.authentication.sso import getGoogleSSO
from main.app.authentication.constants import (
    COOKIE_NAME,
    COOKIE_ACCESS_NAME,
    COOKIE_PATH,
    COOKIE_SAMESITE,
    TOKEN_EXPIRY_HOURS,
)
from main.app.authentication.session import SessionManager
from fastapi import Body

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


def isSecureScheme(request: Request) -> bool:
    return request.url.scheme == "https" if request.url.scheme else False


def issueSessionCookie(response, request, db, user, *, oauth: bool = False) -> str:
    userAgent = request.headers.get("User-Agent", "")
    expiresAt = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRY_HOURS)
    session = SessionManager.createSession(db, user["userId"], userAgent, request, expiresAt)
    accessToken, _ = createAccessToken(data={"userId": str(user["userId"]), "sessionId": str(session.sessionId)})

    if oauth:
        useSecure = isSecureScheme(request)
        response.set_cookie(
            key=COOKIE_NAME,
            value=accessToken,
            httponly=True,
            secure=useSecure,
            samesite=COOKIE_SAMESITE,
            path=COOKIE_PATH,
        )
        response.set_cookie(
            key=COOKIE_ACCESS_NAME,
            value=accessToken,
            httponly=False,
            secure=useSecure,
            samesite=COOKIE_SAMESITE,
            path=COOKIE_PATH,
        )
    else:
        useCookieSecure = isSecureScheme(request)
        response.set_cookie(
            key=COOKIE_NAME,
            value=accessToken,
            httponly=True,
            secure=useCookieSecure,
            samesite=COOKIE_SAMESITE,
            path=COOKIE_PATH,
        )
    return accessToken


@router.get("/health")
def health(request: Request):
    return {"status": "ok", "service": "authentication"}


@router.post("/register")
@limiter.limit("10/minute")
def register(
    request: Request,
    response: Response,
    username: str = Body(..., min_length=1, max_length=100),
    email: str = Body(..., min_length=5, max_length=255),
    password: str = Body(..., min_length=6, max_length=128),
    db: Session = Depends(getSession),
):
    try:
        AuthenticationManager.createUserAccount(db, username, email, password)

        user = AuthenticationManager.authenticateUser(db, username, password)
        if not user:
            raise HTTPException(status_code=401, detail="Auto-login failed after registration")

        accessToken = issueSessionCookie(response, request, db, user)

        return {"message": "success", "accessToken": accessToken, "tokenType": "bearer", "user": user}
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Registration validation error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail="Registration failed. Invalid input.")
    except Exception as e:
        logger.error("Unexpected error during registration", exc_info=True)
        raise HTTPException(status_code=500, detail="Registration failed. Internal error.")


@router.post("/login")
@limiter.limit("10/minute")
def login(
    request: Request,
    response: Response,
    username: str = Body(..., min_length=1, max_length=100),
    password: str = Body(..., min_length=6, max_length=128),
    db: Session = Depends(getSession),
):
    user = AuthenticationManager.authenticateUser(db, username, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    accessToken = issueSessionCookie(response, request, db, user)

    return {"accessToken": accessToken, "tokenType": "bearer", "user": user}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(getSession)):
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
        except Exception as e:
            logger.debug(f"Logout token verification failed: {e}")

    useCookieSecure = isSecureScheme(request)
    response.delete_cookie(
        key=COOKIE_NAME, httponly=True, secure=useCookieSecure, samesite=COOKIE_SAMESITE, path=COOKIE_PATH
    )
    return {"message": "Successfully logged out"}


@router.get("/google")
@limiter.limit("5/minute")
async def googleLogin(request: Request):
    logger.info("Google Login")

    redirectUrl = request.query_params.get("redirect_url", "")
    if not redirectUrl:
        redirectUrl = request.headers.get("referer", "")

    logger.info(f"Redirect URL: {redirectUrl}")

    googleSSO = getGoogleSSO()
    async with googleSSO:
        googleRedirect = await googleSSO.get_login_redirect(state=redirectUrl or None)
    return googleRedirect


@router.get("/callback")
@limiter.limit("5/minute")
async def googleCallback(request: Request, response: Response, db: Session = Depends(getSession)):
    logger.info("--- Google Callback Start ---")

    googleSSO = getGoogleSSO()

    try:
        async with googleSSO:
            userInfo = await googleSSO.verify_and_process(request)

        if not userInfo:
            raise HTTPException(status_code=400, detail="No user info received from Google")

        googleId = userInfo.id
        email = userInfo.email

        logger.info(f"User identified: {email}")
        user = AuthenticationManager.authenticateGoogleUser(db, googleId)

        if not user:
            logger.info("New user detected, creating account...")
            username = email.split("@")[0]
            AuthenticationManager.createUserAccount(db, username=username, email=email, googleId=googleId)
            user = AuthenticationManager.authenticateGoogleUser(db, googleId)

        redirectUrl = googleSSO.state or ""
        if redirectUrl:
            redirectResponse = RedirectResponse(url=redirectUrl)
            issueSessionCookie(redirectResponse, request, db, user, oauth=True)
            return redirectResponse

        accessToken = issueSessionCookie(response, request, db, user, oauth=True)
        logger.info("--- Google Callback End ---")
        return {"accessToken": accessToken, "tokenType": "bearer", "user": user}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Critical error in Google callback: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error during Google login")
