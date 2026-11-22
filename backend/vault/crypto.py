"""Encryption for stored vault secrets (password field only — see the design's
Technical Plan for why title/username/url/notes stay plaintext).

Server-side, not zero-knowledge: the backend holds the key and can decrypt on
demand. Kept free of any other dependency so round-tripping is trivially
testable (encrypt then decrypt returns the original string).
"""

from __future__ import annotations

from cryptography.fernet import Fernet
from django.conf import settings


def _fernet() -> Fernet:
    return Fernet(settings.VAULT_ENCRYPTION_KEY)


def encrypt_secret(plaintext: str) -> bytes:
    return _fernet().encrypt(plaintext.encode("utf-8"))


def decrypt_secret(ciphertext: bytes) -> str:
    return _fernet().decrypt(bytes(ciphertext)).decode("utf-8")
