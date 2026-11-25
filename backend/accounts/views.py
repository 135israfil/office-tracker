from django.contrib.auth import login, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import AuthToken, generate_auth_token, hash_token
from .serializers import CurrentUserSerializer, LoginSerializer


@method_decorator(ensure_csrf_cookie, name="get")
class CsrfView(APIView):
    """Hands the SPA a CSRF cookie before it attempts any unsafe request."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({"detail": "CSRF cookie set."})


class LoginView(APIView):
    permission_classes = [AllowAny]
    # Login is the one endpoint worth rate limiting hard: it is the only place where
    # guessing is useful to an attacker.
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        login(request, user)
        return Response(CurrentUserSerializer(user).data)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(CurrentUserSerializer(request.user).data)


class TokenLoginView(APIView):
    """Login for native clients: a bearer token instead of a session cookie.

    Deliberately does not call `django.contrib.auth.login()` — no session is created,
    so this stays stateless the way a token issuance should be. The token is shown
    exactly once, same convention as a device token's registration response.
    """

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        token = generate_auth_token()
        AuthToken.objects.create(user=user, token_hash=hash_token(token))
        return Response(
            {"token": token, "user": CurrentUserSerializer(user).data},
            status=status.HTTP_201_CREATED,
        )


class TokenRevokeView(APIView):
    """Logout for native clients: delete the token this request authenticated with.

    A no-op (400) if the caller authenticated by session instead — there is no bearer
    token on this request to revoke.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not isinstance(request.auth, AuthToken):
            return Response(
                {"detail": "This request was not authenticated with a token."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        request.auth.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
