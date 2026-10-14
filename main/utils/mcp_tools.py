"""Derive MCP tools from FastAPI routes.

FastMCP hides only its own `uncalled_for.Depends` parameters
(fastmcp/server/dependencies.py:752 -> uncalled_for/introspection.py:43), so a
function that still carries `fastapi.Depends` defaults leaks them into the tool
schema. Enable a route as a tool by giving it an `operation_id`: that attribute
already names the tool and marks the MCP surface in this repo.

The signature/annotation transfer below is FastMCP's own recipe
(fastmcp/server/dependencies.py:805-812); do not invent a variant.
"""

import copy
import inspect
import logging
from typing import Any, Callable, get_type_hints

from fastapi import params as fastapiParams
from fastapi.routing import APIRoute, APIRouter
from fastmcp import FastMCP

logger = logging.getLogger(__name__)

_AUTH_PARAM = "authorization"
_IDENTITY_PARAM = "currentUser"
_SESSION_PARAM = "db"


def withoutAlias(fieldInfo: fastapiParams.FieldInfo) -> fastapiParams.FieldInfo:
    """Copy a Query/Body FieldInfo without its alias.

    pydantic derives the schema property name from the alias, which would
    rename the tool argument (`fromIso` -> `from`). Constraints live in
    `metadata` and are copied untouched.
    """
    stripped = copy.copy(fieldInfo)
    stripped.alias = None
    stripped.validation_alias = None
    stripped.serialization_alias = None
    return stripped


def buildToolFunction(
    route: APIRoute, resolveIdentity: Callable[[str, Any], dict], sessionFactory: Callable[[], Any]
) -> Callable[..., Any]:
    routeFn = route.endpoint
    signature = inspect.signature(routeFn)
    hidden = {
        name for name, parameter in signature.parameters.items() if isinstance(parameter.default, fastapiParams.Depends)
    }

    parameters = [
        parameter
        if not isinstance(parameter.default, fastapiParams.FieldInfo)
        else parameter.replace(default=withoutAlias(parameter.default))
        for name, parameter in signature.parameters.items()
        if name not in hidden
    ]
    parameters.append(
        inspect.Parameter(_AUTH_PARAM, kind=inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=str, default="")
    )

    try:
        annotations = get_type_hints(routeFn)
    except Exception:  # pragma: no cover - unresolved forward reference
        annotations = dict(getattr(routeFn, "__annotations__", {}))

    def tool(**kwargs: Any) -> Any:
        # shortcut: identity/session are injected by these exact names, this
        # repo's route convention; generalise if a route renames its DI params.
        authorization = kwargs.pop(_AUTH_PARAM, "")
        db = sessionFactory()
        try:
            currentUser = resolveIdentity(authorization, db)
            return routeFn(**{**kwargs, _IDENTITY_PARAM: currentUser, _SESSION_PARAM: db})
        finally:
            db.close()

    newSignature = signature.replace(
        parameters=parameters,
        return_annotation=annotations.get("return", signature.return_annotation),
    )
    tool.__signature__ = newSignature  # type: ignore[attr-defined]
    tool.__annotations__ = {
        name: annotation for name, annotation in annotations.items() if name not in hidden and name != "return"
    }
    tool.__annotations__[_AUTH_PARAM] = str
    tool.__name__ = str(route.operation_id)
    tool.__doc__ = routeFn.__doc__
    tool.__module__ = routeFn.__module__
    tool.__qualname__ = f"{routeFn.__qualname__}_tool"
    return tool


def wireRouteTools(
    mcp: FastMCP,
    router: APIRouter,
    *,
    resolveIdentity: Callable[[str, Any], dict],
    sessionFactory: Callable[[], Any],
) -> list[str]:
    """Register one MCP tool per route that declares an `operation_id`."""
    names: list[str] = []
    for route in router.routes:
        if not isinstance(route, APIRoute) or not route.operation_id:
            continue
        mcp.tool(buildToolFunction(route, resolveIdentity, sessionFactory))
        names.append(str(route.operation_id))
    logger.info("wireRouteTools: registered %s", names)
    return names
