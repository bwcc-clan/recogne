from starlette.authentication import AuthenticationError

from ._authz_policy import AuthzPolicy


class PolicyAuthorizationError(AuthenticationError):
    def __init__(self, msg: str, policy: AuthzPolicy) -> None:
        super().__init__(msg)
        self.policy = policy
