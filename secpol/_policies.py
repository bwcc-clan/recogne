from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Awaitable, NamedTuple, Optional, Union, cast

from fastapi.requests import Request
from starlette._utils import is_async_callable

PolicyCheckResult = NamedTuple(
    "PolicyCheckResult", [("allowed", bool), ("failure_reason", Optional[str])]
)


class AuthzPolicy(ABC):
    """Abstract base class for an authorization policy."""

    @abstractmethod
    def check(
        self, request: Request
    ) -> PolicyCheckResult | Awaitable[PolicyCheckResult]:
        """
        Performs the policy check. This can be a synchronous or asynchronous function.

        Args:
            request (Request): The current request, which the policy must authorize.

        Raises:
            NotImplementedError: _description_

        Returns:
            bool | Awaitable[bool]: _description_
        """
        raise NotImplementedError

    @property
    def description(self) -> str:
        """
        Gets a human-friendly description of the policy.

        Returns:
            str: The policy description.
        """
        return type(self).__name__


class Allow(AuthzPolicy):
    """An authorization policy that is satisfied by any request."""

    def check(self, request: Request) -> PolicyCheckResult:
        return PolicyCheckResult(True, None)


class Disallow(AuthzPolicy):
    """An authorization policy that is never satisfied by any request."""

    def check(self, request: Request) -> PolicyCheckResult:
        return PolicyCheckResult(True, "Policy disallows authorization")


class Authenticated(AuthzPolicy):
    """An authorization policy that requires an authenticated user."""

    def check(self, request: Request) -> PolicyCheckResult:
        return PolicyCheckResult(
            request.user.is_authenticated, "User not authenticated"
        )


class Requires(AuthzPolicy):
    """An authorization policy that requires all of the specified scopes to be present."""

    def __init__(self, scopes: Union[str, Sequence[str]]) -> None:
        super().__init__()
        self.scopes = [scopes] if isinstance(scopes, str) else list(scopes)

    def check(self, request: Request) -> PolicyCheckResult:
        for scope in self.scopes:
            if scope not in request.auth.scopes:
                return PolicyCheckResult(False, f"Scope {scope} not present")
        return PolicyCheckResult(True, None)


class AllOf(AuthzPolicy):
    """
    A policy that aggregates one or more sub-policies. All of the sub-policies must pass for the composite policy to
    pass.

    Args:
        AuthzPolicy (_type_): One or more sub-policies to compose into a single policy.
    """

    def __init__(self, *args: AuthzPolicy) -> None:
        super().__init__()
        self.policies = [*args]

    async def check(self, request: Request) -> PolicyCheckResult:
        for policy in self.policies:
            result = await do_policy_check(request, policy)
            if not result.allowed:
                return PolicyCheckResult(
                    False,
                    f"Policy authorization rejected by sub-policy {policy.description}",
                )
        return PolicyCheckResult(True, None)


class OneOf(AuthzPolicy):
    """
    A policy that aggregates one or more sub-policies. At least one sub-policy must pass for the composite policy to
    pass.

    Args:
        AuthzPolicy (_type_): One or more sub-policies to compose into a single policy.
    """

    def __init__(self, *args: AuthzPolicy) -> None:
        super().__init__()
        self.policies = [*args]

    async def check(self, request: Request) -> PolicyCheckResult:
        for policy in self.policies:
            result = await do_policy_check(request, policy)
            if result.allowed:
                return PolicyCheckResult(True, None)
        return PolicyCheckResult(False, "Not authorized by any sub-policy")


async def do_policy_check(request: Request, policy: AuthzPolicy) -> PolicyCheckResult:
    if is_async_callable(policy.check):
        result = await cast(Awaitable[PolicyCheckResult], policy.check(request))
    else:
        result = cast(PolicyCheckResult, policy.check(request))
    return result
