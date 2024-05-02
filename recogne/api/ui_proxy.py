
from urllib.parse import urlparse

from starlette.types import ASGIApp

from .asgiproxy import (
    BaseURLProxyConfigMixin,
    ProxyConfig,
    ProxyContext,
    make_simple_proxy_app,
)


def make_proxy_app(upstream_base_url: str) -> tuple[ASGIApp, ProxyContext]:
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

