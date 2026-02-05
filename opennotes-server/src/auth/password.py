import base64
import hashlib
import hmac

import bcrypt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_argon2_hasher = PasswordHasher(
    memory_cost=19456,
    time_cost=2,
    parallelism=1,
)


def verify_password(plain_password: str, hashed_password: str) -> tuple[bool, bool]:
    """Verify a plain password against a hashed password

    Handles bcrypt (for passwords), Argon2id (for tokens), and SHA256 (legacy tokens).

    Returns:
        tuple[bool, bool]: (is_valid, needs_rehash)
            - is_valid: True if password matches
            - needs_rehash: True if the hash uses legacy SHA256 format and should be upgraded
    """
    if hashed_password.startswith("argon2$"):
        return _verify_argon2(plain_password, hashed_password)
    if hashed_password.startswith("sha256$"):
        return _verify_legacy_sha256(plain_password, hashed_password)
    return _verify_bcrypt(plain_password, hashed_password)


def _verify_argon2(plain_password: str, hashed_password: str) -> tuple[bool, bool]:
    """Verify password against Argon2id hash."""
    try:
        argon2_hash = hashed_password[7:]
        _argon2_hasher.verify(argon2_hash, plain_password)
        return (True, False)
    except (VerifyMismatchError, Exception):
        return (False, False)


def _verify_legacy_sha256(plain_password: str, hashed_password: str) -> tuple[bool, bool]:
    """Verify password against legacy SHA256 hash. Returns needs_rehash=True if valid."""
    try:
        salt_and_hash = base64.b64decode(hashed_password[7:])
        salt = salt_and_hash[:16]
        stored_hash = salt_and_hash[16:]

        plain_password_bytes = plain_password.encode("utf-8")
        salted = salt + plain_password_bytes
        computed_hash = hashlib.sha256(salted).digest()

        is_valid = hmac.compare_digest(computed_hash, stored_hash)
        return (is_valid, is_valid)
    except Exception:
        return (False, False)


def _verify_bcrypt(plain_password: str, hashed_password: str) -> tuple[bool, bool]:
    """Verify password against bcrypt hash."""
    plain_password_bytes = plain_password.encode("utf-8")
    hashed_password_bytes = hashed_password.encode("utf-8")
    try:
        is_valid = bcrypt.checkpw(plain_password_bytes, hashed_password_bytes)
        return (is_valid, False)
    except Exception:
        return (False, False)


def get_password_hash(password: str) -> str:
    """Generate a hash for the given password or token

    For passwords (< 72 bytes): Uses bcrypt with salt
    For tokens (>= 72 bytes): Uses Argon2id (OWASP 2025: m=19456, t=2, p=1)
    """
    if password is None:
        raise ValueError("Password cannot be None")

    password_bytes = password.encode("utf-8")

    if len(password_bytes) >= 72:
        argon2_hash = _argon2_hasher.hash(password)
        return f"argon2${argon2_hash}"

    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")
