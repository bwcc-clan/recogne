
from typing import Any

from fastapi.requests import Request
from starlette.authentication import (
    AuthCredentials,
    AuthenticationBackend,
    SimpleUser,
)
from starlette.requests import HTTPConnection

from .secpol import AuthzPolicy


class MyTestPolicy(AuthzPolicy):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__()
        self.args = kwargs

    def check(self, request: Request) -> bool:
        return True



class BasicAuthBackend(AuthenticationBackend):
    async def authenticate(self, conn: HTTPConnection):

        return AuthCredentials(["scope1"]), SimpleUser("dummy")
