
import asyncio
from urllib.parse import urlparse

import uvicorn
from fastapi import FastAPI
from starlette.types import ASGIApp

from .asgiproxy import (
    BaseURLProxyConfigMixin,
    ProxyConfig,
    ProxyContext,
    make_simple_proxy_app,
)


def make_app(upstream_base_url: str) -> tuple[ASGIApp, ProxyContext]:
    config = type(
        "Config",
        (BaseURLProxyConfigMixin, ProxyConfig),
        {
            "upstream_base_url": upstream_base_url,
            "rewrite_host_header": urlparse(upstream_base_url).netloc,
        },
    )()
    proxy_context = ProxyContext(config)
    app = make_simple_proxy_app(proxy_context)
    return (app, proxy_context)

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello World"}


def main():
    appx, proxy_context = make_app(upstream_base_url="http://localhost:5173/ui/")
    try:
        app.mount("/ui", appx, name="front-end")
        return uvicorn.run(host="0.0.0.0", port=8000, app=app, reload=False)
    finally:
        asyncio.run(proxy_context.close())

if __name__ == "__main__":
    main()
