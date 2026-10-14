"""Derive MCP tools from FastAPI routes.

FastMCP hides only its own `uncalled_for.Depends`, so a route's `fastapi.Depends` parameters would leak into the tool
schema. A route opts in by declaring an `operation_id`: it names the tool and marks the MCP surface in this repo. The
signature/annotation transfer below is FastMCP's own recipe (fastmcp/server/dependencies.py:805-812).
"""

import copy
import inspect
from typing import Any, Callable

from fastapi import params as fastapiParameters
from fastapi.routing import APIRoute, APIRouter
from fastmcp import FastMCP

authorizationArgumentName = "authorization"


def copyWithoutAlias(fieldInformation: fastapiParameters.FieldInfo) -> fastapiParameters.FieldInfo:
    """Copy a Query/Body FieldInfo with its alias removed.

    pydantic takes the schema property name from the alias (`fromIso` -> `from`), so removing it keeps the tool
    argument name; constraints live in `metadata`, copied untouched.
    """
    copiedFieldInformation = copy.copy(fieldInformation)
    copiedFieldInformation.alias = None
    copiedFieldInformation.validation_alias = None
    copiedFieldInformation.serialization_alias = None
    return copiedFieldInformation


def buildToolFromRoute(
    route: APIRoute,
    resolveIdentity: Callable[[str, Any], dict],
    sessionFactory: Callable[[], Any],
) -> Callable[..., Any]:
    """Build the MCP tool callable for one route: DI parameters hidden, aliases stripped, identity injected."""
    routeFunction = route.endpoint
    try:
        signature = inspect.signature(routeFunction, eval_str=True)
    except Exception:  # annotations that cannot be resolved stay as strings
        signature = inspect.signature(routeFunction)

    parameters = []
    for parameter in signature.parameters.values():
        if isinstance(parameter.default, fastapiParameters.Depends):
            continue  # FastMCP hides only its own Depends: identity and session must not reach the schema
        if isinstance(parameter.default, fastapiParameters.FieldInfo):
            parameter = parameter.replace(default=copyWithoutAlias(parameter.default))
        parameters.append(parameter)
    parameters.append(
        inspect.Parameter(
            authorizationArgumentName,
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=str,
            default="",
        )
    )

    def toolCallable(**kwargs: Any) -> Any:
        # shortcut: identity and session are injected by these exact names (this repo's route convention).
        authorization = kwargs.pop(authorizationArgumentName, "")
        databaseSession = sessionFactory()
        try:
            identity = resolveIdentity(authorization, databaseSession)
            return routeFunction(**{**kwargs, "currentUser": identity, "db": databaseSession})
        finally:
            databaseSession.close()

    toolCallable.__signature__ = signature.replace(parameters=parameters)  # type: ignore[attr-defined]
    toolCallable.__annotations__ = {
        parameter.name: parameter.annotation
        for parameter in parameters
        if parameter.annotation is not inspect.Parameter.empty
    }
    toolCallable.__name__ = str(route.operation_id)
    toolCallable.__doc__ = routeFunction.__doc__
    toolCallable.__module__ = routeFunction.__module__
    toolCallable.__qualname__ = f"{routeFunction.__qualname__}_tool"
    return toolCallable


def mcpToolDecorator(
    mcpServer: FastMCP,
    router: APIRouter,
    *,
    resolveIdentity: Callable[[str, Any], dict],
    sessionFactory: Callable[[], Any],
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Build the decorator that registers a route endpoint as an MCP tool.

    Stack it ABOVE `@router.<verb>(...)`: the `APIRoute` and its `operation_id` only exist after the FastAPI
    decorator has run, and a route missing either raises here.
    """

    def registerTool(routeFunction: Callable[..., Any]) -> Callable[..., Any]:
        route = next(
            (
                candidateRoute
                for candidateRoute in reversed(router.routes)
                if isinstance(candidateRoute, APIRoute) and candidateRoute.endpoint is routeFunction
            ),
            None,
        )
        if route is None or not route.operation_id:
            raise RuntimeError(
                f"{routeFunction.__qualname__}: needs an APIRoute stacked above @router.<verb>(...) "
                "and its operation_id to become an MCP tool"
            )
        mcpServer.tool(buildToolFromRoute(route, resolveIdentity, sessionFactory))
        return routeFunction

    return registerTool
