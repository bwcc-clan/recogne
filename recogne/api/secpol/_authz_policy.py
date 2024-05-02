from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from typing import Any, Awaitable, ParamSpec, TypeVar, Union

import wrapt
from fastapi.requests import Request
from starlette._utils import is_async_callable

POLICY_CLASS_ATTRIBUTE_NAME = "_authz_policy_class_"
POLICY_PARAMS_ATTRIBUTE_NAME = "_authz_policy_params_"


Param = ParamSpec("Param")
RetType = TypeVar("RetType")


class AuthzPolicy(ABC):
    @abstractmethod
    def check(self, request: Request) -> bool | Awaitable[bool]:
        raise NotImplementedError


class Authenticated(AuthzPolicy):
    def check(self, request: Request) -> bool | Awaitable[bool]:
        return request.user.is_authenticated


class Requires(AuthzPolicy):
    def __init__(self, *, scopes: Union[str, Sequence[str]]) -> None:
        super().__init__()
        self.scopes = [scopes] if isinstance(scopes, str) else list(scopes)

    def check(self, request: Request) -> bool | Awaitable[bool]:
        for scope in self.scopes:
            if scope not in request.auth.scopes:
                return False
        return True


# pyright: basic
# Based on example at https://github.com/GrahamDumpleton/wrapt/issues/150#issuecomment-893232442
def authz_policy(policy: type[AuthzPolicy], **params: Any):
    """
    A decorator that applies an authorization policy to the endpoint.
    """
    def wrapper(wrapped: Callable[Param, RetType]) -> Callable[Param, RetType]:
        @wrapt.decorator
        async def _async_authz(wrapped, instance, args, kwargs):
            return await wrapped(*args, **kwargs)

        @wrapt.decorator
        def _sync_authz(wrapped, instance, args, kwargs):
            return wrapped(*args, **kwargs)

        setattr(wrapped, POLICY_CLASS_ATTRIBUTE_NAME, policy)
        setattr(wrapped, POLICY_PARAMS_ATTRIBUTE_NAME, params)

        if is_async_callable(wrapped):
            return _async_authz(wrapped)  # type: ignore
        else:
            return _sync_authz(wrapped)  # type: ignore

    return wrapper
