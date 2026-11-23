import hashlib
import ipaddress
import logging
import re
from config import Config, getSession, LOCALHOST_ADDRESSES

from datetime import datetime, timedelta, timezone
from main.utils.logging_config import limiter

from fastapi import APIRouter, Response, HTTPException, Request, Depends, Body
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from main.app.authentication.authentication import AuthenticationManager
from main.app.authentication.util import (
    MAX_PASSWORD_BYTES,
    createAccessToken,
    passwordExceedsByteLimit,
    verifyAccessToken,
)
from fastapi_sso.sso.base import SSOLoginError
from main.app.authentication.sso import getGoogleSSO
from main.app.authentication.constants import (
    COOKIE_NAME,
    COOKIE_PATH,
    COOKIE_SAMESITE,
    TOKEN_EXPIRY_HOURS,
)
from main.app.authentication.session import SessionManager
from main.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


COOKIE_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$"
)


def resolveCookieDomain(request: Request) -> str | None:
    hostname = request.url.hostname or "localhost"
    if hostname in LOCALHOST_ADDRESSES:
        return None
    try:
        ipaddress.ip_address(hostname)
        return None
    except ValueError:
        pass
    if not COOKIE_DOMAIN_RE.fullmatch(hostname):
        return None
    return hostname


def isSafeOAuthResume(target: str) -> bool:
    if not target or not target.startswith("/") or target.startswith("//"):
        return False
    if "\\" in target:
        return False
    from urllib.parse import parse_qs, urlparse

    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return False
    if parsed.path not in ("/oauth/login", "/wallet/mcp/oauth/login"):
        return False
    requestIds = parse_qs(parsed.query).get("request_id", [])
    return len(requestIds) == 1 and bool(requestIds[0])


def issueSessionCookie(response, request, db, user) -> str:
    userAgent = request.headers.get("User-Agent", "")
    expiresAt = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRY_HOURS)
    session = SessionManager.createSession(db, user["userId"], userAgent, expiresAt)
    accessToken = createAccessToken(data={"userId": str(user["userId"]), "sessionId": str(session.sessionId)})

    cookieDomain = resolveCookieDomain(request)

    response.set_cookie(
        key=COOKIE_NAME,
        value=accessToken,
        httponly=True,
        secure=True,
        samesite=COOKIE_SAMESITE,
        path=COOKIE_PATH,
        domain=cookieDomain,
    )
    return str(session.sessionId)


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
    if passwordExceedsByteLimit(password):
        raise HTTPException(status_code=400, detail=f"Password must be at most {MAX_PASSWORD_BYTES} bytes")
    try:
        AuthenticationManager.createUserAccount(db, username, email, password)

        user = AuthenticationManager.authenticateUser(db, username, password)
        if not user:
            raise HTTPException(status_code=401, detail="Auto-login failed after registration")

        issueSessionCookie(response, request, db, user)

        return {"message": "success", "user": user}
    except HTTPException as e:
        if e.status_code == 400:
            raise HTTPException(status_code=400, detail="Registration failed.")
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
    if passwordExceedsByteLimit(password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user = AuthenticationManager.authenticateUser(db, username, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    issueSessionCookie(response, request, db, user)

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

    response.delete_cookie(
        key=COOKIE_NAME,
        httponly=True,
        secure=True,
        samesite=COOKIE_SAMESITE,
        path=COOKIE_PATH,
        domain=resolveCookieDomain(request),
    )
    return {"message": "Successfully logged out"}


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

        if getattr(userInfo, "email_verified", None) is False:
            raise HTTPException(status_code=401, detail="SSO email not verified")

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
            sessionId = issueSessionCookie(redirectResponse, request, db, user)
            SessionManager.revokeAllExcept(db, user["userId"], sessionId)
            return redirectResponse

        if isSafeOAuthResume(state_param):
            resumeResponse = RedirectResponse(url=state_param)
            resumeSessionId = issueSessionCookie(resumeResponse, request, db, user)
            SessionManager.revokeAllExcept(db, user["userId"], resumeSessionId)
            return resumeResponse

        sessionId = issueSessionCookie(response, request, db, user)
        SessionManager.revokeAllExcept(db, user["userId"], sessionId)
        logger.info("--- Google Callback End ---")
        return {"user": user}

    except SSOLoginError:
        logger.warning("SSO state validation failed", exc_info=True)
        raise HTTPException(status_code=401, detail="SSO login failed.")
    except HTTPException:
        raise
    except Exception:
        logger.error("Critical error in Google callback", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error during Google login")
