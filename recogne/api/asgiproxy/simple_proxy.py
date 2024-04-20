from typing import Any, Protocol

from starlette.types import ASGIApp, Receive, Scope, Send

from .context import ProxyContext
from .proxies.http import proxy_http
from .proxies.websocket import proxy_websocket


class ProxyCallable(Protocol):
    """Enables us to type the ASGI handlers."""
    async def __call__(self, *, context: ProxyContext, scope: Scope, receive: Receive, send: Send) -> Any:
        pass

def make_simple_proxy_app(
    proxy_context: ProxyContext,
    *,
    proxy_http_handler: ProxyCallable=proxy_http,
    proxy_websocket_handler: ProxyCallable=proxy_websocket,
) -> ASGIApp:
    """
    Given a ProxyContext, return a simple ASGI application that can proxy
    HTTP and WebSocket connections.

    The handlers for the protocols can be overridden and/or removed with the
    respective parameters.
    """

    async def app(scope: Scope, receive: Receive, send: Send):  # noqa: ANN201
        if scope["type"] == "lifespan":
            return None  # We explicitly do nothing here for this simple app.

        if scope["type"] == "http" and proxy_http_handler:
            return await proxy_http_handler(
                context=proxy_context, scope=scope, receive=receive, send=send
            )

        if scope["type"] == "websocket" and proxy_websocket_handler:
            return await proxy_websocket_handler(
                context=proxy_context, scope=scope, receive=receive, send=send
            )

        raise NotImplementedError(f"Scope {scope} is not understood or no handler is configured")

    return app
