"""Endpoint-specific abuse controls for public authentication routes."""

from rest_framework.throttling import SimpleRateThrottle


class EndpointRateThrottle(SimpleRateThrottle):
    """Throttle only matching URL names and methods.

    Keeping these controls endpoint-specific prevents health checks and
    ordinary authenticated API traffic from consuming the login budget.
    """

    url_names = frozenset()
    methods = frozenset({"POST"})
    identify_authenticated_user = False

    def get_cache_key(self, request, view):
        match = getattr(request, "resolver_match", None)
        if request.method not in self.methods or not match or match.url_name not in self.url_names:
            return None

        if self.identify_authenticated_user and request.user.is_authenticated:
            ident = f"user-{request.user.pk}"
        else:
            ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


class LoginRateThrottle(EndpointRateThrottle):
    scope = "login"
    url_names = frozenset({"jwt-create"})


class TokenRefreshRateThrottle(EndpointRateThrottle):
    scope = "token_refresh"
    url_names = frozenset({"jwt-refresh"})


class SignupRateThrottle(EndpointRateThrottle):
    scope = "signup"
    url_names = frozenset({"customuser-list"})


class PasswordResetRateThrottle(EndpointRateThrottle):
    scope = "password_reset"
    url_names = frozenset({
        "customuser-reset-password",
        "customuser-reset-password-confirm",
    })


class AccountStatusRateThrottle(EndpointRateThrottle):
    scope = "account_status"
    url_names = frozenset({"account-status"})


class RealtimeTicketRateThrottle(EndpointRateThrottle):
    scope = "realtime_ticket"
    url_names = frozenset({"realtime-ticket"})
    identify_authenticated_user = True
