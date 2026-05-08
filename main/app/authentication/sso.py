from fastapi_sso.sso.google import GoogleSSO

from config import Config


def getGoogleSSO(redirectUri: str | None = None) -> GoogleSSO:
    if not redirectUri:
        redirectUri = Config.USER.get("GOOGLE_REDIRECT_URI", "")

    return GoogleSSO(
        client_id=Config.USER.get("GOOGLE_CLIENT_ID", ""),
        client_secret=Config.USER.get("GOOGLE_CLIENT_SECRET", ""),
        redirect_uri=redirectUri,
    )
