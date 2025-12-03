"""
Encryption service for secure API key storage.

Provides multi-layered encryption with key rotation support using Fernet
(symmetric encryption) with PBKDF2 key derivation.
"""

import base64
import secrets

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class EncryptionService:
    """
    Service for encrypting and decrypting API keys.

    Uses PBKDF2 key derivation with per-record salts to derive encryption keys
    from a master key. Supports key rotation through versioned key identifiers.

    Attributes:
        master_key: Master encryption key (stored in environment, never in database)
        key_cache: Cache of derived Fernet instances for performance
    """

    def __init__(self, master_key: str) -> None:
        """
        Initialize encryption service with a master key.

        Args:
            master_key: URL-safe base64-encoded master encryption key (must decode to 32 bytes / 256 bits)

        Raises:
            ValueError: If master key is invalid or has insufficient length
        """
        try:
            key_bytes = base64.urlsafe_b64decode(master_key.encode())
        except Exception as e:
            raise ValueError(f"Master key must be valid URL-safe base64. Error: {e}") from e

        if len(key_bytes) != 32:
            raise ValueError(
                f"Master key must decode to exactly 32 bytes (256 bits). Got {len(key_bytes)} bytes."
            )

        self.master_key = key_bytes
        self.key_cache: dict[str, Fernet] = {}

    def _derive_key(self, salt: bytes) -> bytes:
        """
        Derive an encryption key from the master key and salt using PBKDF2.

        Uses SHA256 with 480,000 iterations (OWASP 2023 recommendation).

        Args:
            salt: Unique salt for this encryption operation

        Returns:
            URL-safe base64-encoded encryption key
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        derived = kdf.derive(self.master_key)
        return base64.urlsafe_b64encode(derived)

    def encrypt_api_key(self, api_key: str) -> tuple[bytes, str, str]:
        """
        Encrypt an API key using a newly generated salt.

        Args:
            api_key: Plain text API key to encrypt

        Returns:
            Tuple of (encrypted_data, key_id, preview) where:
            - encrypted_data: Encrypted API key as bytes
            - key_id: Versioned identifier (format: "v1:hex_salt") for key rotation
            - preview: Last 4 characters of the API key (format: "...XXXX")
        """
        salt = secrets.token_bytes(16)
        key_id = f"v1:{salt.hex()}"

        derived_key = self._derive_key(salt)
        fernet = Fernet(derived_key)
        encrypted = fernet.encrypt(api_key.encode())

        preview = f"...{api_key[-4:]}" if len(api_key) >= 4 else "..."

        return encrypted, key_id, preview

    def decrypt_api_key(self, encrypted_data: bytes, key_id: str) -> str:
        """
        Decrypt an API key using the stored key identifier.

        Args:
            encrypted_data: Encrypted API key bytes
            key_id: Versioned key identifier (format: "v1:hex_salt")

        Returns:
            Decrypted API key as string

        Raises:
            ValueError: If key version is unsupported
            cryptography.fernet.InvalidToken: If decryption fails
        """
        if key_id in self.key_cache:
            fernet = self.key_cache[key_id]
        else:
            version, salt_hex = key_id.split(":", 1)
            if version != "v1":
                raise ValueError(f"Unsupported key version: {version}")

            salt = bytes.fromhex(salt_hex)
            derived_key = self._derive_key(salt)
            fernet = Fernet(derived_key)
            self.key_cache[key_id] = fernet

        decrypted = fernet.decrypt(encrypted_data)
        return decrypted.decode()

    def rotate_key(self, encrypted_data: bytes, old_key_id: str) -> tuple[bytes, str, str]:
        """
        Rotate encryption key by re-encrypting with a new salt.

        Args:
            encrypted_data: Currently encrypted API key
            old_key_id: Current key identifier

        Returns:
            Tuple of (new_encrypted_data, new_key_id, preview)
        """
        plaintext = self.decrypt_api_key(encrypted_data, old_key_id)
        return self.encrypt_api_key(plaintext)

    def clear_cache(self) -> None:
        """Clear the key derivation cache."""
        self.key_cache.clear()
