from typing import Optional

from fastapi.applications import FastAPI
from starlette.authentication import AuthenticationBackend
from starlette.middleware.authentication import AuthenticationMiddleware

from ._authz_policy import Authenticated, AuthzPolicy, Requires, authz_policy
from ._exceptions import PolicyAuthorizationError
from ._secure_route import PolicyFactory, SecureRoute


def add_endpoint_security(
    app: FastAPI,
    *,
    backend: AuthenticationBackend,
    policy_factory: Optional[PolicyFactory] = None,
) -> None:
    app.add_middleware(AuthenticationMiddleware, backend=backend)
    if policy_factory:
        SecureRoute.policy_factory = policy_factory
    app.router.route_class = SecureRoute


__all__ = [
    "authz_policy",
    "SecureRoute",
    "PolicyAuthorizationError",
    "AuthzPolicy",
    "Authenticated",
    "Requires",
]
