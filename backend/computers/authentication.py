"""Device-token authentication for agent endpoints (§29).

Deliberately *not* added to `DEFAULT_AUTHENTICATION_CLASSES`. A device token grants
exactly one thing — the right to report this machine's own activity — and wiring it in
globally would quietly make it usable against every session-auth endpoint in the
project. Agent views opt in explicitly.
"""

from rest_framework import authentication, exceptions

from employees.models import EmployeeStatus

from .models import Computer, ComputerStatus, hash_token

KEYWORD = "Device"


class DeviceTokenAuthentication(authentication.BaseAuthentication):
    """`Authorization: Device <token>`.

    Returns `(user, computer)` so views can reach the machine through `request.auth`
    while permission and audit code keeps working with a real user object. `request.user`
    is the owning employee's account, which is what activity is attributed to.
    """

    keyword = KEYWORD

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).split()
        if not header or header[0].decode().lower() != self.keyword.lower():
            return None
        if len(header) == 1:
            raise exceptions.AuthenticationFailed("Device token missing.")
        if len(header) > 2:
            raise exceptions.AuthenticationFailed("Device token must not contain spaces.")

        token = header[1].decode()
        computer = (
            Computer.objects.select_related("employee", "employee__user")
            .filter(device_token_hash=hash_token(token))
            .first()
        )
        # One message for "no such token" and "wrong token": distinguishing them tells
        # an attacker which half of the guess was right.
        if computer is None:
            raise exceptions.AuthenticationFailed("Invalid device token.")

        if computer.status == ComputerStatus.DISABLED:
            raise exceptions.AuthenticationFailed("This device has been disabled.")
        if computer.employee.status != EmployeeStatus.ACTIVE:
            raise exceptions.AuthenticationFailed("The employee for this device is inactive.")
        if not computer.employee.user.is_active:
            raise exceptions.AuthenticationFailed("The employee for this device is inactive.")

        return (computer.employee.user, computer)

    def authenticate_header(self, request):
        # Without this DRF answers 403 instead of 401 for an unauthenticated request.
        return self.keyword
