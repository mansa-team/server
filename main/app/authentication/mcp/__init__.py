from main.app.authentication.mcp.login import (
    oauthResumePath,
    registerLoginRoutes,
)
from main.app.authentication.mcp.provider import (
    SoloAuth,
    SoloOAuthProvider,
)

__all__ = [
    "SoloAuth",
    "SoloOAuthProvider",
    "oauthResumePath",
    "registerLoginRoutes",
]
