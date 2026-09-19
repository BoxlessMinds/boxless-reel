"""SQLAlchemy model for a user's connected Google OAuth credential."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class GoogleOAuthCredential(Base):
    """SQLAlchemy model for a per-user Google OAuth credential.

    One row per app user (unique on ``user_id``). ``access_token`` and
    ``refresh_token`` are Fernet-encrypted at rest by the repository layer
    (`src.repositories.google_oauth_repository.GoogleOAuthRepository`) via
    the shared `src.utils.encryption.get_encryption()` singleton — this
    model never sees plaintext tokens.

    ``oauth_client_id``/``oauth_client_secret`` are reserved for a future
    bring-your-own-credentials option. They are nullable, always ``NULL``
    in v1, and no code path reads or writes them yet.
    """

    __tablename__ = "google_oauth_credentials"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, unique=True, index=True
    )

    google_account_email: Mapped[str] = mapped_column(String(255), nullable=False)
    google_account_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # Fernet ciphertext, never plaintext. See GoogleOAuthRepository.
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)

    token_expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    scopes: Mapped[str] = mapped_column(String(500), nullable=False)

    # Reserved for a future bring-your-own-credentials option. Unused in v1.
    oauth_client_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    oauth_client_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        """Return string representation of the credential.

        Deliberately omits access_token/refresh_token so a stray log or
        debugger print can never leak them, ciphertext or not.
        """
        return (
            f"<GoogleOAuthCredential(id={self.id}, user_id={self.user_id}, "
            f"google_account_email={self.google_account_email!r}, "
            f"token_expires_at={self.token_expires_at})>"
        )
