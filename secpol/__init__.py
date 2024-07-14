"""
This package adds policy-based security to a Starlette ASGI application.
"""

from fastapi.applications import FastAPI
from starlette.authentication import AuthenticationBackend
from starlette.middleware.authentication import AuthenticationMiddleware

from ._authz_policy import PolicyAuthorizationError, SecureRoute, authz_policy
from ._policies import (
    AllOf,
    Allow,
    Authenticated,
    AuthzPolicy,
    Disallow,
    OneOf,
    PolicyCheckResult,
    Requires,
)


def add_endpoint_security(
    app: FastAPI,
    *,
    backend: AuthenticationBackend,
    default_policy: AuthzPolicy = Allow()
) -> None:
    """
    Adds policy-based security middleware.

    After an app is configured with this function, route endpoints can be assigned an authorization policy by using the
    `@authz_policy` decorator. The decorator works with both sync and async endpoint functions.

    Example:
        The example below adds the `Authenticated` policy, which requires an authenticated user in order to access the
        endpoint::

            from fastapi import FastAPI
            from secpol import Authenticated, add_endpoint_security, authz_policy

            app = FastAPI()
            add_endpoint_security(app, backend=BasicAuthBackend())


            @app.get("/")
            @authz_policy(Authenticated())
            async def root():
                return {"message": "Hello World"}

    Args:
        app (FastAPI):
            The application to configure with policy-based security.

        backend (AuthenticationBackend):
            The authentication backend to use with the authentication middleware.

        default_policy (AuthzPolicy, optional):
            The default policy to use if an endpoint is not explicitly decorated with a policy. Defaults to allowing
            access to the endpoint.
    """
    app.add_middleware(AuthenticationMiddleware, backend=backend)
    app.router.route_class = SecureRoute
    SecureRoute.default_policy = default_policy


__all__ = [
    SecureRoute.__name__,
    authz_policy.__name__,
    PolicyCheckResult.__name__,
    PolicyAuthorizationError.__name__,
    AuthzPolicy.__name__,
    Allow.__name__,
    Disallow.__name__,
    Authenticated.__name__,
    AllOf.__name__,
    OneOf.__name__,
    Requires.__name__,
] # type: ignore
