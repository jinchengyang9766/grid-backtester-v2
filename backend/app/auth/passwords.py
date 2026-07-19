"""Argon2id password hashing (SPEC Sections 24.2 and 37).

Plaintext passwords are never returned, logged, or persisted; only the
complete encoded Argon2id hash leaves this module. Hashing configuration
lives here, never in the ORM User model.
"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

__all__ = ["hash_password", "verify_password"]

# Library-recommended default work factors; the default type is Argon2id.
# Salts are generated internally per hash — never supplied manually.
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Return the complete encoded Argon2id hash for the given password."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Return True only when the password matches the stored encoded hash.

    Wrong passwords, malformed hashes, and unsupported/corrupt hash values
    all return False — a bad stored hash must never surface as a 500.
    """
    try:
        return _hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError):
        return False
