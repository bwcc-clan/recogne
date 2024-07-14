"""
This package adds policy-based security to a Starlette ASGI application.
"""

from typing import Optional

from fastapi.applications import FastAPI
from starlette.authentication import AuthenticationBackend
from starlette.middleware.authentication import AuthenticationMiddleware

from ._authz_policy import (
    Authenticated,
    AuthzPolicy,
    PolicyFactory,
    Requires,
    authz_policy,
)
from ._exceptions import PolicyAuthorizationError
from ._policies import Composite
from ._secure_route import SecureRoute


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
    "SecureRoute",
    "authz_policy",
    "PolicyAuthorizationError",
    "PolicyFactory",
    "AuthzPolicy",
    "Authenticated",
    "Composite",
    "Requires",
]
