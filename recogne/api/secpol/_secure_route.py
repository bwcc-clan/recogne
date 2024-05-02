import asyncio
from collections.abc import Callable, Coroutine
from typing import Any, Protocol

from fastapi.requests import Request
from fastapi.responses import Response
from fastapi.routing import APIRoute

from . import PolicyAuthorizationError
from ._authz_policy import (
    POLICY_CLASS_ATTRIBUTE_NAME,
    POLICY_PARAMS_ATTRIBUTE_NAME,
    AuthzPolicy,
)


class PolicyFactory(Protocol):
    def __call__(
        self, request: Request, policy_class: type[AuthzPolicy], **kwargs: Any
    ) -> AuthzPolicy: ...


def default_policy_factory(
    request: Request, policy_class: type[AuthzPolicy], **kwargs: Any
) -> AuthzPolicy:
    return policy_class(**kwargs)


class SecureRoute(APIRoute):
    policy_factory: PolicyFactory = default_policy_factory

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            await self._invoke_policy_check(request)
            return await original_route_handler(request)

        return custom_route_handler

    async def _invoke_policy_check(self, request: Request):
        policy_type = getattr(self.dependant.call, POLICY_CLASS_ATTRIBUTE_NAME, None)
        if not policy_type:
            return
        policy_params = getattr(self.dependant.call, POLICY_PARAMS_ATTRIBUTE_NAME, {})
        policy = SecureRoute.policy_factory(request, policy_type, **policy_params)
        if asyncio.iscoroutinefunction(policy.check):
            allowed = await policy.check(request)
        else:
            allowed = policy.check(request)
        if not allowed:
            raise PolicyAuthorizationError("Not authorized by policy", policy)
