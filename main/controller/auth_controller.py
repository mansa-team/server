from fastapi import APIRouter, Response, Depends, Body, HTTPException
from fastapi.responses import RedirectResponse
import urllib.parse

from main.app.auth.auth import *
from main.utils.util import log

router = APIRouter(
    prefix="/auth",
    tags=["Auth"]
)

@router.get("/health")
def health():
    return {"status": "ok", "service": "auth"}

@router.post("/register")
def register(response: Response, username: str = Body(...), email: str = Body(...), password: str = Body(...)):
    try:
        createUserAccount(username, email, password)

        user = authenticateUser(username, password)
        if not user:
            raise HTTPException(status_code=401, detail="Auto-login failed after registration")
            
        accessToken = createAccessToken(data={"userId": str(user["userId"])})
        
        response.set_cookie(
            key="mansa_token",
            value=accessToken,
            httponly=True,
            secure=True,
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
def login(response: Response, username: str = Body(...), password: str = Body(...)):
    user = authenticateUser(username, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    accessToken = createAccessToken(data={"userId": str(user["userId"])})
    
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

@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(
        key="mansa_token",
        httponly=True,
        secure=True,
        samesite="lax"
    )
    return {"message": "Successfully logged out"}

@router.get("/google")
def googleLogin():
    clientId = Config.AUTH['GOOGLE_CLIENT.ID']
    redirectUri = Config.AUTH['GOOGLE_REDIRECT.URI']
    
    params = {
        "client_id": clientId,
        "redirect_uri": redirectUri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account"
    }
    
    queryString = urllib.parse.urlencode(params)
    googleUrl = f"https://accounts.google.com/o/oauth2/v2/auth?{queryString}"
    
    return RedirectResponse(googleUrl)

@router.get("/callback")
def googleCallback(response: Response, code: str):
    log("auth", "--- Google Callback Start ---")
    log("auth", f"Code received: {code[:10]}...")
    
    clientId = Config.AUTH['GOOGLE_CLIENT.ID']
    clientSecret = Config.AUTH['GOOGLE_CLIENT.SECRET']
    redirectUri = Config.AUTH['GOOGLE_REDIRECT.URI']

    try:
        log("auth", "Exchanging code for token...")
        tokenUrl = "https://oauth2.googleapis.com/token"
        tokenData = {
            "code": code,
            "client_id": clientId,
            "client_secret": clientSecret,
            "redirect_uri": redirectUri,
            "grant_type": "authorization_code",
        }
        
        tokenRes = requests.post(tokenUrl, data=tokenData, timeout=15)
        log("auth", f"Token response status: {tokenRes.status_code}")
        
        if not tokenRes.ok:
            log("auth", f"ERROR: Token exchange failed: {tokenRes.text}")
            raise HTTPException(status_code=400, detail="Failed to retrieve token from Google")
        
        tokenJson = tokenRes.json()
        accessTokenGoogle = tokenJson.get("access_token")
        
        if not accessTokenGoogle:
            raise HTTPException(status_code=400, detail="No access token in Google response")

        log("auth", "Fetching user info...")
        userInfoUrl = "https://www.googleapis.com/oauth2/v3/userinfo"
        userInfoRes = requests.get(userInfoUrl, headers={"Authorization": f"Bearer {accessTokenGoogle}"}, timeout=15)
        log("auth", f"UserInfo response status: {userInfoRes.status_code}")
        
        if not userInfoRes.ok:
            log("auth", f"ERROR: UserInfo fetch failed: {userInfoRes.text}")
            raise HTTPException(status_code=400, detail="Failed to retrieve user info from Google")
        
        googleUser = userInfoRes.json()
        googleId = googleUser.get("sub")
        email = googleUser.get("email")
        
        log("auth", f"User identified: {email}")

        log("auth", "Verifying database records...")
        user = authenticateGoogleUser(googleId)
        
        if not user:
            log("auth", "New user detected, creating account...")
            username = email.split('@')[0]
            createUserAccount(username=username, email=email, googleId=googleId)
            user = authenticateGoogleUser(googleId)
            log("auth", "Account created successfully.")

        log("auth", "Generating local JWT session...")
        accessToken = createAccessToken(data={"userId": str(user["userId"])})
        
        response = RedirectResponse(url=f"http://127.0.0.1:5500/main/test/auth.html#token={accessToken}")
        
        response.set_cookie(
            key="mansa_token",
            value=accessToken,
            httponly=False,
            secure=False, 
            samesite="lax",
            path="/" 
        )

        log("auth", "SUCCESS: Redirecting to frontend.")
        log("auth", "--- Google Callback End ---")
        return response

    except requests.exceptions.Timeout:
        log("auth", "ERROR: Google API request timed out")
        raise HTTPException(status_code=504, detail="Google API connection timed out")
    except Exception as e:
        log("auth", f"CRITICAL ERROR in callback: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error during Google login")

@router.get("/me")
async def getMe(user: dict = Depends(getCurrentUser)):
    return {
        "status": "success",
        "user": user
    }

@router.get("/admin")
async def adminTest(user: dict = Depends(getCurrentUser)):
    if not checkAccessLevel(user["level"], levels["Admin"]):
        raise HTTPException(status_code=403, detail="Insufficient access level")
    return {
        "status": "success",
        "message": "Admin area access granted",
        "user": user
    }