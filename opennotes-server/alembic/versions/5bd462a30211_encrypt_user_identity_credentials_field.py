"""encrypt_user_identity_credentials_field

Revision ID: 5bd462a30211
Revises: d445875ad611
Create Date: 2025-10-30 17:22:00.618520

This migration adds encryption to the UserIdentity.credentials field.

Technical details:
- The field remains JSONB at the database level
- Encryption is handled transparently by the EncryptedJSONB TypeDecorator
- Encrypted data is stored as: {"encrypted": "base64_fernet_ciphertext"}
- The TypeDecorator handles backward compatibility during the transition

Data migration strategy:
- Existing unencrypted credentials will be automatically encrypted on next write
- The TypeDecorator's process_result_value handles both encrypted and unencrypted data
- No immediate data migration required, but all writes will use encrypted format

Security notes:
- Requires CREDENTIALS_ENCRYPTION_KEY environment variable
- Uses Fernet encryption (AES-128 CBC with HMAC authentication)
- Key rotation would require re-encrypting all existing credentials
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5bd462a30211"
down_revision: str | Sequence[str] | None = "d445875ad611"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Apply encryption to UserIdentity credentials field.

    No schema changes are needed since EncryptedJSONB is still JSONB at the
    database level. This migration serves as documentation of the encryption
    implementation.

    All new writes will automatically use encrypted format. Existing data
    will be read as plaintext and re-encrypted on next update.
    """
    op.execute(
        """
        COMMENT ON COLUMN user_identities.credentials IS
        'Encrypted provider-specific credential data. Encrypted using Fernet (AES-128 CBC + HMAC). Format: {"encrypted": "base64_ciphertext"}'
        """
    )


def downgrade() -> None:
    """
    Remove encryption from UserIdentity credentials field.

    WARNING: Downgrading will remove the comment but will NOT decrypt existing
    encrypted data. Manual data migration would be required to decrypt all
    credentials before downgrading.
    """
    op.execute(
        """
        COMMENT ON COLUMN user_identities.credentials IS
        'Provider-specific credential data stored as JSON'
        """
    )
