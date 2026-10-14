import copy
import inspect
from typing import Any, Callable

from fastapi import params as fastapiParameters
from fastapi.routing import APIRoute, APIRouter
from fastmcp import FastMCP


def copyWithoutAlias(fieldInformation: fastapiParameters.FieldInfo) -> fastapiParameters.FieldInfo:
    fieldInfo = copy.copy(fieldInformation)
    fieldInfo.alias = None
    fieldInfo.validation_alias = None
    fieldInfo.serialization_alias = None
    return fieldInfo


def buildToolFromRoute(
    route: APIRoute,
    resolveIdentity: Callable[[str, Any], dict],
    sessionFactory: Callable[[], Any],
) -> Callable[..., Any]:
    routeFunction = route.endpoint
    try:
        signature = inspect.signature(routeFunction, eval_str=True)
    except Exception:
        signature = inspect.signature(routeFunction)

    parameters = []
    for parameter in signature.parameters.values():
        if isinstance(parameter.default, fastapiParameters.Depends):
            continue
        if isinstance(parameter.default, fastapiParameters.FieldInfo):
            parameter = parameter.replace(default=copyWithoutAlias(parameter.default))
        parameters.append(parameter)
    parameters.append(
        inspect.Parameter(
            "authorization",
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=str,
            default="",
        )
    )

    def toolCallable(**kwargs: Any) -> Any:
        authorization = kwargs.pop("authorization", "")
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
