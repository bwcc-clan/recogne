import asyncio

import uvicorn
from fastapi import FastAPI

from secpol import (
    AllOf,
    Authenticated,
    Requires,
    add_endpoint_security,
    authz_policy,
)

from .auth import BasicAuthBackend, MyTestPolicy
from .ui_proxy import make_proxy_app

app = FastAPI()
add_endpoint_security(app, backend=BasicAuthBackend())


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/test")
@authz_policy(MyTestPolicy(excellent=True))
async def root_test(arg: str):
    return {"message": f"Hello, {arg}"}


@app.get("/test-auth")
@authz_policy(Authenticated())
async def test_auth(arg: str):
    return {"message": f"Hello, {arg}"}


@app.get("/test-composite")
@authz_policy(AllOf(Authenticated(), Requires(scopes="scope1")))
async def test_composite(arg: str):
    return {"message": f"Hello, {arg}"}


@app.get("/test-requires")
@authz_policy(Requires(scopes=["scope1"]))
async def test_requires(arg: str):
    return {"message": f"Hello, {arg}"}


def main():
    appx, proxy_context = make_proxy_app(upstream_base_url="http://localhost:5173/ui/")
    try:
        app.mount("/ui", appx, name="front-end")
        return uvicorn.run(host="0.0.0.0", port=8000, app=app, reload=False)
    finally:
        asyncio.run(proxy_context.close())


if __name__ == "__main__":
    main()
