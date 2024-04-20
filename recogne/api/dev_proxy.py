from urllib.parse import urlparse, urlunsplit

import httpx
from starlette._utils import get_route_path
from starlette.background import BackgroundTask
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.types import Receive, Scope, Send


class DevProxy:
    def __init__(self, target: str) -> None:
        parse_result = urlparse(target)
        if parse_result.params or parse_result.fragment:
            raise ValueError("target must not include query params, or fragment")
        scheme = parse_result.scheme or "http"
        path = parse_result.path.strip("/")
        self.config_checked = False
        self.target = urlunsplit((scheme, parse_result.netloc, path, "", ""))
        self.client = httpx.AsyncClient()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        The ASGI entry point.
        """

        if scope["type"] != "http":
            pass

        if not self.config_checked:
            await self.check_config()
            self.config_checked = True

        path = self.get_path(scope)
        response = await self.get_response(path, scope, receive)
        await response(scope, receive, send)

    def get_path(self, scope: Scope) -> str:
        """
        Given the ASGI scope, return the `path` string to serve up,
        with OS specific path separators, and any '..', '.' components removed.
        """
        route_path = get_route_path(scope)
        return route_path

    async def get_response(self, path: str, scope: Scope, receive: Receive) -> Response:
        """
        Returns an HTTP response, given the incoming path, method and request headers.
        """
        if scope["method"] not in ("GET", "HEAD"):
            raise HTTPException(status_code=405)

        assert scope["type"] == "http"
        request = Request(scope, receive)
        url = self.target + path

        async with httpx.AsyncClient() as client:
            req = client.build_request(
                scope["method"], url=url, headers=request.headers
            )
            resp: httpx.Response | None = None
            try:
                resp = await client.send(req, stream=True)
                return StreamingResponse(
                    resp.aiter_text(),
                    status_code=resp.status_code,
                    headers=resp.headers,
                    background=BackgroundTask(resp.aclose),
                )
            except httpx.ConnectError:
                return Response(
                    "Unable to connect to target server",
                    media_type="text/plain",
                    status_code=500,
                )
            except:
                if resp:
                    await resp.aclose()
                raise

    async def check_config(self) -> None:
        """
        Perform a one-off configuration check that DevProxy is actually
        pointed at another server, so that we can raise loud errors rather than
        just returning 404 responses.
        """
        if self.target is None:  # type: ignore
            return
