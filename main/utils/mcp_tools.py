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
from typing import Any, Callable, get_type_hints

from fastapi import params as fastapiParams
from fastapi.routing import APIRoute, APIRouter
from fastmcp import FastMCP

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


def mcpToolFor(
    mcp: FastMCP,
    router: APIRouter,
    *,
    resolveIdentity: Callable[[str, Any], dict],
    sessionFactory: Callable[[], Any],
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Build a decorator that registers a route endpoint as an MCP tool.

    Stack it ABOVE `@router.<verb>(...)`, as the outermost decorator: the
    `APIRoute` object (and its `operation_id`) only exists after the FastAPI
    decorator has run. `operation_id` names the tool and marks the MCP surface;
    a route without one is never exposed and raises here.
    """

    def decorator(routeFn: Callable[..., Any]) -> Callable[..., Any]:
        route = next(
            (r for r in reversed(router.routes) if isinstance(r, APIRoute) and r.endpoint is routeFn),
            None,
        )
        if route is None:
            raise RuntimeError(
                f"{routeFn.__qualname__}: no APIRoute for this endpoint; "
                "stack the MCP decorator above @router.<verb>(...)"
            )
        if not route.operation_id:
            raise RuntimeError(f"{routeFn.__qualname__}: route needs an operation_id to become an MCP tool")
        mcp.tool(buildToolFunction(route, resolveIdentity, sessionFactory))
        return routeFn

    return decorator
