from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed


class SingleSessionJWTAuthentication(JWTAuthentication):
    """Only the most recent login per account is accepted.

    Every login rotates the user's session_id and stamps it into the token
    as `sid`; a token minted by an earlier login carries a stale sid and is
    rejected with code `session_replaced` so the frontend can explain why
    the user was signed out.
    """

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if str(validated_token.get("sid", "")) != str(user.session_id):
            raise AuthenticationFailed(
                {
                    "detail": "You were signed out because this account signed in on another device.",
                    "code": "session_replaced",
                },
                code="session_replaced",
            )
        return user
