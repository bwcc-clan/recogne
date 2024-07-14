
from typing import Any

from fastapi.requests import Request
from starlette.authentication import (
    AuthCredentials,
    AuthenticationBackend,
    SimpleUser,
)
from starlette.requests import HTTPConnection

from secpol import AuthzPolicy, PolicyCheckResult


class MyTestPolicy(AuthzPolicy):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__()
        self.args = kwargs

    def check(self, request: Request) -> PolicyCheckResult:
        return PolicyCheckResult(True, None)



class BasicAuthBackend(AuthenticationBackend):
    async def authenticate(self, conn: HTTPConnection):

        return AuthCredentials(["scope1"]), SimpleUser("dummy")
