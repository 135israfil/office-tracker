"""Bearer-token authentication for native clients (the Android app).

Global, unlike `computers.authentication.DeviceTokenAuthentication`: a device token
grants one machine the right to report its own activity, so it stays opt-in per view.
A bearer token here carries full user identity — the same thing a session cookie
already grants a browser — so every existing permission class behaves identically
regardless of which authentication class populated `request.user`.
"""

from django.utils import timezone
from rest_framework import authentication, exceptions

from .models import AuthToken, hash_token

KEYWORD = "Bearer"


class BearerTokenAuthentication(authentication.BaseAuthentication):
    """`Authorization: Bearer <token>`."""

    keyword = KEYWORD

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).split()
        if not header or header[0].decode().lower() != self.keyword.lower():
            return None
        if len(header) == 1:
            raise exceptions.AuthenticationFailed("Bearer token missing.")
        if len(header) > 2:
            raise exceptions.AuthenticationFailed("Bearer token must not contain spaces.")

        token = header[1].decode()
        auth_token = (
            AuthToken.objects.select_related("user").filter(token_hash=hash_token(token)).first()
        )
        # One message for "no such token" and "wrong token": distinguishing them tells
        # an attacker which half of the guess was right.
        if auth_token is None:
            raise exceptions.AuthenticationFailed("Invalid token.")
        if not auth_token.user.is_active:
            raise exceptions.AuthenticationFailed("This account is disabled.")

        AuthToken.objects.filter(pk=auth_token.pk).update(last_used_at=timezone.now())
        return (auth_token.user, auth_token)

    def authenticate_header(self, request):
        # Without this DRF answers 403 instead of 401 for an unauthenticated request.
        return self.keyword
