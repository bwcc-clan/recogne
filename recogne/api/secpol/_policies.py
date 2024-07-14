from collections.abc import Sequence
from typing import Any, Tuple

from fastapi.requests import Request
from starlette._utils import is_async_callable

from ._authz_policy import AuthzPolicy, PolicyFactory
from ._exceptions import PolicyAuthorizationError

type PolicySpec = Tuple[type[AuthzPolicy], dict[str, Any]]


class Composite(AuthzPolicy):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__()
        policies: Sequence[PolicySpec] = kwargs.get("policies", [])
        policy_factory: PolicyFactory | None = kwargs.get("_policy_factory")
        if not policy_factory:
            raise RuntimeError("_policy_factory not in kwargs")
        self.policy_factory = policy_factory
        self.policies = policies

    async def check(self, request: Request) -> bool:
        for policy_spec in self.policies:
            policy = self.policy_factory(request=request, policy_class=policy_spec[0], **policy_spec[1])
            if is_async_callable(policy.check):
                allowed = await policy.check(request)
            else:
                allowed = policy.check(request)
            if not allowed:
                raise PolicyAuthorizationError("Not authorized by sub-policy", policy)
        return True

