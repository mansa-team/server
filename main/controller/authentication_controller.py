import hashlib
import hmac
import logging
from config import Config, getSession, LOCALHOST_ADDRESSES

from datetime import datetime, timedelta, timezone
from main.utils.logging_config import limiter

from fastapi import APIRouter, Response, HTTPException, Request, Depends, Body
from fastapi.responses import RedirectResponse
from fastapi_sso.sso.base import SSOLoginError
from sqlalchemy.orm import Session

from main.app.authentication.authentication import AuthenticationManager
from main.app.authentication.csrf import CSRF_COOKIE_NAME, csrf_exempt, issueCsrfToken
from main.app.authentication.introspect import introspectToken
from main.app.authentication.service_token import verifyServiceToken
from main.app.authentication.util import createAccessToken, verifyAccessToken
from main.app.authentication.sso import getGoogleSSO
from main.app.authentication.constants import (
    COOKIE_NAME,
    COOKIE_PATH,
    COOKIE_SAMESITE,
    TOKEN_EXPIRY_HOURS,
)
from main.app.authentication.session import SessionManager
from main.models.user import User
from main.utils.security_headers import getRequestScheme

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


def isSecureScheme(request: Request) -> bool:
    # X-Forwarded-Proto trusted for scheme detection behind proxies/TLS
    # terminators. Cookie `Secure` itself is always set (see below) so a
    # spoofed `X-Forwarded-Proto: http` can never downgrade it.
    return getRequestScheme(request) == "https"


def resolveCookieDomain(request: Request) -> str | None:
    hostname = request.url.hostname or "localhost"
    # Local hosts get a host-only cookie (no Domain attribute): a cookie with
    # Domain=localhost is never sent back to 127.0.0.1, which surfaces as 401
    # "Session not found" on every cookie-authenticated route.
    if hostname in ("localhost", "127.0.0.1"):
        return None
    return hostname


def issueSessionCookie(response, request, db, user) -> tuple[str, str]:
    userAgent = request.headers.get("User-Agent", "")
    expiresAt = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRY_HOURS)
    session = SessionManager.createSession(db, user["userId"], userAgent, expiresAt)
    accessToken = createAccessToken(data={"userId": str(user["userId"]), "sessionId": str(session.sessionId)})

    cookieDomain = resolveCookieDomain(request)

    # Secure-always: browsers send Secure cookies over https and over
    # http://localhost (trustworthy loopback), so local dev keeps working
    # while LAN/plain-http can never carry the session.
    response.set_cookie(
        key=COOKIE_NAME,
        value=accessToken,
        httponly=True,
        secure=True,
        samesite=COOKIE_SAMESITE,
        path=COOKIE_PATH,
        domain=cookieDomain,
    )
    issueCsrfToken(response, request)
@csrf_exempt
    return accessToken, str(session.sessionId)


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

        accessToken, _ = issueSessionCookie(response, request, db, user)

        # Cookie-only: token travels via HttpOnly Secure cookie, never JSON.
        return {"message": "success", "user": user}
    except HTTPException as e:
        if e.status_code == 400:
            raise HTTPException(status_code=400, detail="Registration failed.")
@csrf_exempt
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

    accessToken, sessionId = issueSessionCookie(response, request, db, user)
    SessionManager.revokeAllExcept(db, user["userId"], sessionId)

    # Cookie-only: token travels via HttpOnly Secure cookie, never JSON.
    return {"user": user}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(getSession)):
    token = request.headers.get("X-Access-Token")
    if not token:
        authHeader = request.headers.get("Authorization")
        if authHeader and authHeader.startswith("Bearer "):
            token = authHeader.split(" ")[1]
    if not token:
        token = request.cookies.get(COOKIE_NAME)

    if token:
        try:
            payload = verifyAccessToken(token)
            userId = payload.get("userId")
            sessionId = payload.get("sessionId")
            if userId and sessionId:
                try:
                    SessionManager.revokeSession(db, sessionId, userId)
                except (ValueError, TypeError):
                    pass
        except Exception as e:
            logger.debug(f"Logout token verification failed: {e}")

    useCookieSecure = True  # Secure-always: matches issueSessionCookie
    response.delete_cookie(
        key=COOKIE_NAME,
        httponly=True,
        secure=useCookieSecure,
        samesite=COOKIE_SAMESITE,
        path=COOKIE_PATH,
        domain=resolveCookieDomain(request),
    )
    response.delete_cookie(
        key=CSRF_COOKIE_NAME,
        secure=True,
        samesite=COOKIE_SAMESITE,
        path=COOKIE_PATH,
        domain=resolveCookieDomain(request),
    )
    return {"message": "Successfully logged out"}


@router.get("/csrf")
def getCsrfToken(request: Request, response: Response):
    """Issue/refresh the double-submit CSRF token for cookie sessions."""
    token = request.cookies.get(CSRF_COOKIE_NAME) or issueCsrfToken(response, request)
    # If the cookie already existed, re-stamp it so the browser keeps it;
    # issueCsrfToken already set it when missing.
    return {"csrfToken": token}


@router.post("/introspect")
@limiter.limit("30/minute")
def introspect(
    request: Request,
    db: Session = Depends(getSession),
@csrf_exempt
    token: str | None = Body(default=None, embed=True),
):
    if not verifyServiceToken(request.headers.get("X-Service-Token", "")):
        raise HTTPException(status_code=401, detail="Unauthorized")
    auth = request.headers.get("Authorization", "")
    raw = (
        token
        or request.headers.get("X-Access-Token")
        or (auth.split(" ")[1] if auth.startswith("Bearer ") else None)
        or request.cookies.get(COOKIE_NAME)
    )
    if not raw:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        return introspectToken(db, raw)
    except HTTPException:
@csrf_exempt
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/google")
@limiter.limit("5/minute")
async def googleLogin(request: Request):
    logger.info("Google login initiated")

    redirectUrl = request.query_params.get("redirect_url", "")
    if not redirectUrl:
        redirectUrl = request.headers.get("referer", "")

    googleSSO = getGoogleSSO()
    async with googleSSO:
        googleRedirect = await googleSSO.get_login_redirect(state=redirectUrl or None)

    return googleRedirect


@router.get("/callback")
@limiter.limit("5/minute")
async def googleCallback(request: Request, response: Response, db: Session = Depends(getSession)):
    logger.info("--- Google Callback Start ---")

    state_param = request.query_params.get("state", "")

    googleSSO = getGoogleSSO()

    try:
        async with googleSSO:
            userInfo = await googleSSO.verify_and_process(request)

        if not userInfo:
            raise HTTPException(status_code=400, detail="No user info received from Google")

        googleId = userInfo.id
        email = userInfo.email

        if not googleId or not email:
            raise HTTPException(status_code=400, detail="Incomplete user info from Google")

        logger.info("Google user identified")
        user = AuthenticationManager.authenticateGoogleUser(db, googleId)

        if not user:
            logger.info("New user detected, creating account...")
            baseUsername = email.split("@")[0]
            username = baseUsername
            suffix = 0
            for _ in range(100):
                try:
                    AuthenticationManager.createUserAccount(db, username=username, email=email, googleId=googleId)
                    break
                except HTTPException as e:
                    if e.status_code != 400:
                        raise
                    if db.query(User).filter(User.username == username).first() is None:
                        raise
                    suffix += 1
                    username = f"{baseUsername}{suffix}"
            else:
                raise HTTPException(status_code=400, detail="Registration failed.")
            user = AuthenticationManager.authenticateGoogleUser(db, googleId)

        redirectUrl = ""
        if state_param.startswith("http"):
            from urllib.parse import urlparse

            parsed = urlparse(state_param)
            host = parsed.hostname or ""
            if host in LOCALHOST_ADDRESSES or host.endswith(".localhost"):
                redirectUrl = state_param

        if redirectUrl:
            redirectResponse = RedirectResponse(url=redirectUrl)
            _, sessionId = issueSessionCookie(redirectResponse, request, db, user)
            SessionManager.revokeAllExcept(db, user["userId"], sessionId)
            return redirectResponse

        accessToken, sessionId = issueSessionCookie(response, request, db, user)
        SessionManager.revokeAllExcept(db, user["userId"], sessionId)
        logger.info("--- Google Callback End ---")
        # Cookie-only: token travels via HttpOnly Secure cookie, never JSON.
        return {"user": user}

    except HTTPException:
        raise
    except SSOLoginError:
        logger.warning("SSO state validation failed", exc_info=True)
        raise HTTPException(status_code=401, detail="SSO login failed.")
    except Exception:
        logger.error("Critical error in Google callback", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error during Google login")
