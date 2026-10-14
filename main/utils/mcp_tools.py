"""Derive MCP tools from FastAPI routes.

FastMCP hides only its own `uncalled_for.Depends`, so a route's `fastapi.Depends` params leak into the tool
schema. A route opts in by declaring an `operation_id`: the tool name and this repo's MCP-surface marker.
The signature/annotation transfer below is FastMCP's own recipe (fastmcp/server/dependencies.py:805-812).
"""

import copy
import inspect
from typing import Any, Callable, get_type_hints

from fastapi import params as fastapiParams
from fastapi.routing import APIRoute, APIRouter
from fastmcp import FastMCP

_AUTH_PARAM = "authorization"


def withoutAlias(fieldInfo: fastapiParams.FieldInfo) -> fastapiParams.FieldInfo:
    """Copy a Query/Body FieldInfo without its alias.

    pydantic takes the schema property name from the alias (`fromIso` -> `from`), so stripping it keeps
    the tool argument name; constraints live in `metadata`, copied untouched.
    """
    stripped = copy.copy(fieldInfo)
    stripped.alias = stripped.validation_alias = stripped.serialization_alias = None
    return stripped


def buildToolFunction(
    route: APIRoute, resolveIdentity: Callable[[str, Any], dict], sessionFactory: Callable[[], Any]
) -> Callable[..., Any]:
    routeFn = route.endpoint
    signature = inspect.signature(routeFn)
    parameters = []
    for parameter in signature.parameters.values():
        if isinstance(parameter.default, fastapiParams.Depends):
            continue  # FastMCP hides only its own Depends; these must not reach the schema
        if isinstance(parameter.default, fastapiParams.FieldInfo):
            parameter = parameter.replace(default=withoutAlias(parameter.default))
        parameters.append(parameter)
    parameters.append(
        inspect.Parameter(_AUTH_PARAM, kind=inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=str, default="")
    )
    try:
        annotations = get_type_hints(routeFn)
    except Exception:  # pragma: no cover - unresolved forward reference
        annotations = dict(getattr(routeFn, "__annotations__", {}))

    def tool(**kwargs: Any) -> Any:
        # shortcut: identity/session are injected by these exact names (this repo's route convention).
        authorization = kwargs.pop(_AUTH_PARAM, "")
        db = sessionFactory()
        try:
            return routeFn(**{**kwargs, "currentUser": resolveIdentity(authorization, db), "db": db})
        finally:
            db.close()

    tool.__signature__ = signature.replace(  # type: ignore[attr-defined]
        parameters=parameters,
        return_annotation=annotations.get("return", signature.return_annotation),
    )
    tool.__annotations__ = {p.name: annotations[p.name] for p in parameters if p.name in annotations}
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

    Stack it ABOVE `@router.<verb>(...)`: the `APIRoute` and its `operation_id` only exist after the
    FastAPI decorator has run; a route without either raises here.
    """

    def decorator(routeFn: Callable[..., Any]) -> Callable[..., Any]:
        route = next((r for r in reversed(router.routes) if isinstance(r, APIRoute) and r.endpoint is routeFn), None)
        if route is None or not route.operation_id:
            raise RuntimeError(
                f"{routeFn.__qualname__}: needs an APIRoute stacked above @router.<verb>(...) "
                "and its operation_id to become an MCP tool"
            )
        mcp.tool(buildToolFunction(route, resolveIdentity, sessionFactory))
        return routeFn

    return decorator
