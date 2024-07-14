import asyncio
from collections.abc import Awaitable, Callable, Coroutine, Sequence
from typing import Any, ParamSpec, TypeVar, cast

import wrapt
from fastapi.requests import Request
from fastapi.responses import Response
from fastapi.routing import APIRoute
from starlette._utils import is_async_callable
from starlette.authentication import AuthenticationError

from ._policies import AllOf, AuthzPolicy, NullPolicy, PolicyCheckResult

POLICY_ATTRIBUTE_NAME = "_authz_policy_"


Param = ParamSpec("Param")
RetType = TypeVar("RetType")




class PolicyAuthorizationError(AuthenticationError):
    def __init__(self, msg: str, policy: AuthzPolicy) -> None:
        super().__init__(msg)
        self.policy = policy


# pyright: basic
# This decorator can be used to decorate either sync or async functions.
# Based on example at https://github.com/GrahamDumpleton/wrapt/issues/150#issuecomment-893232442
def authz_policy(policy: AuthzPolicy | Sequence[AuthzPolicy]):
    """
    A decorator that applies an authorization policy to the endpoint.
    """

    if isinstance(policy, Sequence):
        policy = AllOf(*policy)

    def wrapper(wrapped: Callable[Param, RetType]) -> Callable[Param, RetType]:
        @wrapt.decorator
        async def _async_authz(wrapped, instance, args, kwargs):
            return await wrapped(*args, **kwargs)

        @wrapt.decorator
        def _sync_authz(wrapped, instance, args, kwargs):
            return wrapped(*args, **kwargs)

        setattr(wrapped, POLICY_ATTRIBUTE_NAME, policy)

        if is_async_callable(wrapped):
            return _async_authz(wrapped)  # type: ignore
        else:
            return _sync_authz(wrapped)  # type: ignore

    return wrapper


class SecureRoute(APIRoute):

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            await self._invoke_policy_check(request)
            return await original_route_handler(request)

        return custom_route_handler

    async def _invoke_policy_check(self, request: Request):
        policy = getattr(self.dependant.call, POLICY_ATTRIBUTE_NAME, NullPolicy())
        if asyncio.iscoroutinefunction(policy.check):
            result = await cast(Awaitable[PolicyCheckResult], policy.check(request))
        else:
            result = cast(PolicyCheckResult, policy.check(request))
        if not result.allowed:
            reason = result.failure_reason if result.failure_reason else "Not authorized by policy"
            raise PolicyAuthorizationError(reason, policy)
