"""
This package adds policy-based security to a Starlette ASGI application.
"""

from fastapi.applications import FastAPI
from starlette.authentication import AuthenticationBackend
from starlette.middleware.authentication import AuthenticationMiddleware

from ._authz_policy import PolicyAuthorizationError, SecureRoute, authz_policy
from ._policies import AllOf, Authenticated, AuthzPolicy, Requires


def add_endpoint_security(
    app: FastAPI,
    *,
    backend: AuthenticationBackend,
) -> None:
    app.add_middleware(AuthenticationMiddleware, backend=backend)
    app.router.route_class = SecureRoute


__all__ = [
    "SecureRoute",
    "authz_policy",
    "PolicyAuthorizationError",
    "AuthzPolicy",
    "Authenticated",
    "AllOf",
    "Requires",
]
