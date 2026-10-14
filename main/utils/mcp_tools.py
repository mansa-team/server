import copy
import inspect
from typing import Any, Callable, cast

from fastapi import Response, params as fastapiParameters
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
    resolveIdentity: Callable[[str, Any], dict] | None = None,
    sessionFactory: Callable[[], Any] | None = None,
) -> Callable[..., Any]:
    routeFunction = route.endpoint
    try:
        signature = inspect.signature(routeFunction, eval_str=True)
    except Exception:
        signature = inspect.signature(routeFunction)

    parameterNames = set(signature.parameters)
    injectIdentity = "currentUser" in parameterNames
    injectSession = "db" in parameterNames
    if injectIdentity and resolveIdentity is None:
        raise RuntimeError(f"{route.operation_id}: declares currentUser but no resolveIdentity was given")
    if (injectIdentity or injectSession) and sessionFactory is None:
        raise RuntimeError(f"{route.operation_id}: declares db but no sessionFactory was given")
    
    identityResolver = cast("Callable[[str, Any], dict]", resolveIdentity)
    sessionProvider = cast("Callable[[], Any]", sessionFactory)

    parameters = []
    responseNames = []
    for parameter in signature.parameters.values():
        if isinstance(parameter.default, fastapiParameters.Depends):
            continue
        if parameter.annotation is Response:
            responseNames.append(parameter.name)
            continue
        if isinstance(parameter.default, fastapiParameters.FieldInfo):
            parameter = parameter.replace(default=copyWithoutAlias(parameter.default))
        parameters.append(parameter)
    if injectIdentity or injectSession:
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
        databaseSession = sessionProvider() if (injectIdentity or injectSession) else None
        try:
            if injectIdentity:
                kwargs["currentUser"] = identityResolver(authorization, databaseSession)
            if injectSession:
                kwargs["db"] = databaseSession
            for name in responseNames:
                kwargs[name] = Response()
            return routeFunction(**kwargs)
        finally:
            if databaseSession is not None:
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
    resolveIdentity: Callable[[str, Any], dict] | None = None,
    sessionFactory: Callable[[], Any] | None = None,
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
