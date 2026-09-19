"""Google OAuth service for connecting a user's YouTube-scoped Google account.

Handles the consent URL, the OAuth callback (state verification + token
exchange), and transparent access-token refresh. This is the only place in
the codebase that talks to Google's OAuth2 endpoints directly; it never
touches the YouTube Data API itself (that belongs to later stories).
"""

import logging
from datetime import datetime, timedelta, timezone
from random import SystemRandom
from string import ascii_letters, digits

import requests
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token as google_id_token
from google.oauth2.credentials import Credentials as GoogleCredentials
from google_auth_oauthlib.flow import Flow
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from src.config import settings
from src.models.google_oauth_credential import GoogleOAuthCredential
from src.models.user import User
from src.repositories.google_oauth_repository import GoogleOAuthRepository
from src.utils.encryption import get_encryption

logger = logging.getLogger(__name__)

# Scopes requested on consent. `youtube` is the scope the acceptance criteria
# name explicitly; `openid`/`userinfo.email` are what let the callback read
# the connecting account's email/id from the ID token.
GOOGLE_OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
GOOGLE_REVOKE_URI = "https://oauth2.googleapis.com/revoke"

STATE_TOKEN_EXPIRE_MINUTES = 10
STATE_TOKEN_TYPE = "oauth_state"

# RFC 7636 PKCE code_verifier: 43-128 chars from the "unreserved" charset.
CODE_VERIFIER_CHARS = ascii_letters + digits + "-._~"
CODE_VERIFIER_LENGTH = 128


def _generate_code_verifier() -> str:
    """Generate a PKCE code verifier.

    `Flow.authorization_url` would auto-generate one itself, but only on
    the `Flow` instance used to build the consent URL — that instance
    doesn't survive to the callback request. Generating it here lets it
    be carried across in the signed `state` JWT instead.
    """
    rnd = SystemRandom()
    return "".join(rnd.choice(CODE_VERIFIER_CHARS) for _ in range(CODE_VERIFIER_LENGTH))

# Refresh an access token proactively once it's within this margin of expiry.
TOKEN_REFRESH_SAFETY_MARGIN = timedelta(minutes=5)


def _utc_now_naive() -> datetime:
    """Current UTC time as a naive datetime.

    `google.oauth2.credentials.Credentials.expiry` and the `token_expires_at`
    DB column are both naive UTC, so comparisons against them must be naive
    too or Python raises on the subtraction.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class GoogleAuthServiceError(Exception):
    """Base exception for Google auth service errors."""

    pass


class GoogleAuthStateError(GoogleAuthServiceError):
    """Raised when the OAuth `state` param is missing, tampered, or expired."""

    pass


class GoogleCredentialNotFoundError(GoogleAuthServiceError):
    """Raised when no Google credential is connected for a user."""

    pass


class GoogleTokenRefreshError(GoogleAuthServiceError):
    """Raised when refreshing an expired Google access token fails."""

    pass


class GoogleAuthService:
    """Service for the Google OAuth account-connection flow.

    Never issues a YouTube Data API call — only the OAuth2 consent/token
    endpoints and one ID-token decode to identify the connecting account.
    """

    def __init__(self, repository: GoogleOAuthRepository) -> None:
        """Initialize the service with its repository.

        Args:
            repository: Repository for Google OAuth credential persistence.
        """
        self.repository = repository

    def _build_flow(self, state: str | None = None) -> Flow:
        """Build a `Flow` configured with the app's shared OAuth client.

        Args:
            state: Optional state value to attach to the flow (needed when
                re-building the flow to exchange a code on callback).

        Returns:
            A configured `google_auth_oauthlib.flow.Flow`.
        """
        client_config = {
            "web": {
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "auth_uri": GOOGLE_AUTH_URI,
                "token_uri": GOOGLE_TOKEN_URI,
                "redirect_uris": [settings.google_oauth_redirect_uri],
            }
        }
        flow = Flow.from_client_config(
            client_config, scopes=GOOGLE_OAUTH_SCOPES, state=state
        )
        flow.redirect_uri = settings.google_oauth_redirect_uri
        return flow

    def _create_state_token(self, user_id: str, code_verifier: str) -> str:
        """Create a short-lived JWT identifying the connecting user.

        Also carries the PKCE `code_verifier` generated for this consent
        request, since it must be reunited with the code at the callback
        but nothing else about this request survives until then. The
        verifier is Fernet-encrypted before being embedded — `state` rides
        the same front-channel redirect as the authorization `code`, so a
        plaintext verifier here would be recoverable by anyone who can see
        the callback URL, defeating the reason PKCE exists.

        Args:
            user_id: The app user initiating the consent flow.
            code_verifier: The PKCE verifier generated for this flow.

        Returns:
            Encoded JWT, signed with the app's existing JWT secret.
        """
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=STATE_TOKEN_EXPIRE_MINUTES
        )
        payload = {
            "sub": user_id,
            "cv": get_encryption().encrypt(code_verifier),
            "exp": expire,
            "type": STATE_TOKEN_TYPE,
        }
        return jwt.encode(
            payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
        )

    def _verify_state_token(self, state: str | None) -> tuple[str, str]:
        """Verify the OAuth callback's `state` param and extract its claims.

        Args:
            state: The `state` query param from Google's redirect.

        Returns:
            A `(user_id, code_verifier)` tuple encoded in the state token.

        Raises:
            GoogleAuthStateError: If `state` is missing, tampered, expired,
                not a token this service issued, or its encrypted
                `code_verifier` claim fails to decrypt.
        """
        if not state:
            logger.warning("Google OAuth callback received no state parameter")
            raise GoogleAuthStateError("Missing state parameter")

        try:
            payload = jwt.decode(
                state, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
            )
        except JWTError as e:
            logger.warning("Google OAuth callback state token invalid: %s", e)
            raise GoogleAuthStateError("Invalid or expired state parameter") from e

        if payload.get("type") != STATE_TOKEN_TYPE:
            logger.warning("Google OAuth callback state token has unexpected type")
            raise GoogleAuthStateError("Invalid state parameter")

        user_id = payload.get("sub")
        encrypted_code_verifier = payload.get("cv")
        if not user_id or not encrypted_code_verifier:
            logger.warning("Google OAuth callback state token missing claims")
            raise GoogleAuthStateError("Invalid state parameter")

        try:
            code_verifier = get_encryption().decrypt(encrypted_code_verifier)
        except ValueError as e:
            logger.warning(
                "Google OAuth callback state token's code_verifier failed to decrypt: %s", e
            )
            raise GoogleAuthStateError("Invalid state parameter") from e

        return user_id, code_verifier

    def build_authorization_url(self, user: User) -> str:
        """Build the Google consent screen URL for a user to connect.

        Uses `access_type="offline"` and `prompt="consent"` together — both
        are load-bearing, not stylistic. Without `access_type="offline"`
        Google never issues a refresh token at all; without `prompt="consent"`
        a user who has already granted access once is silently re-approved
        with no refresh token on the repeat consent. Every later story's
        unattended `get_valid_credential` refresh depends on this pair, so
        neither parameter should be removed.

        Args:
            user: The authenticated app user requesting to connect.

        Returns:
            The Google OAuth authorization URL to redirect the user to.
        """
        code_verifier = _generate_code_verifier()
        state = self._create_state_token(user.id, code_verifier)
        flow = self._build_flow(state=state)
        flow.code_verifier = code_verifier
        authorization_url, _ = flow.authorization_url(
            access_type="offline",
            prompt="consent",
            state=state,
            include_granted_scopes="true",
        )
        logger.debug("Built Google authorization URL for user %s", user.id)
        return authorization_url

    def handle_callback(self, code: str, state: str | None) -> GoogleOAuthCredential:
        """Handle Google's OAuth redirect: verify state, exchange, persist.

        Args:
            code: The authorization code from Google.
            state: The short-lived JWT identifying the connecting user.

        Returns:
            The persisted (encrypted) `GoogleOAuthCredential`.

        Raises:
            GoogleAuthStateError: If `state` is missing, tampered, or expired.
            GoogleAuthServiceError: If the code exchange or account lookup
                fails.
        """
        user_id, code_verifier = self._verify_state_token(state)

        flow = self._build_flow(state=state)
        flow.code_verifier = code_verifier
        try:
            flow.fetch_token(code=code)
        except Exception as e:
            logger.error("Failed to exchange Google authorization code: %s", e)
            raise GoogleAuthServiceError(
                "Failed to exchange Google authorization code"
            ) from e

        credentials = flow.credentials

        try:
            claims = google_id_token.verify_oauth2_token(
                credentials.id_token,
                GoogleAuthRequest(),
                settings.google_oauth_client_id,
                clock_skew_in_seconds=10,
            )
        except Exception as e:
            logger.error("Failed to verify connected Google account: %s", e)
            raise GoogleAuthServiceError(
                "Failed to verify connected Google account"
            ) from e

        google_account_email = claims["email"]
        google_account_id = claims["sub"]
        scopes = " ".join(credentials.scopes or GOOGLE_OAUTH_SCOPES)

        credential = self.repository.upsert(
            user_id=user_id,
            google_account_email=google_account_email,
            google_account_id=google_account_id,
            access_token=credentials.token,
            refresh_token=credentials.refresh_token,
            token_expires_at=credentials.expiry,
            scopes=scopes,
        )
        logger.info(
            "Connected Google account %s for user %s", google_account_email, user_id
        )
        return credential

    def get_status(self, user_id: str) -> GoogleOAuthCredential | None:
        """Plain read of a user's stored credential — no refresh, no network call.

        Used by `GET /status`, which must reflect stored state as-is rather
        than trigger a refresh attempt (and a possible `GoogleTokenRefreshError`)
        on every status check. Use `get_valid_credential` instead when the
        caller is about to make a Data API call.

        Args:
            user_id: The app user to look up.

        Returns:
            The stored `GoogleOAuthCredential`, or `None` if not connected.
        """
        return self.repository.get_by_user_id(user_id)

    def get_valid_credential(self, user_id: str) -> GoogleOAuthCredential:
        """Return a valid credential for a user, refreshing if near expiry.

        This is the method every later story's service calls before hitting
        the YouTube Data API. A refreshed access token is persisted via the
        repository before being returned — a refresh that only returns a new
        in-memory credential without saving it would silently fail on the
        next server restart.

        Args:
            user_id: The app user whose credential to return.

        Returns:
            A `GoogleOAuthCredential` with a non-expired access token.

        Raises:
            GoogleCredentialNotFoundError: If the user has no connected
                Google account.
            GoogleTokenRefreshError: If the access token is near/past expiry
                and refreshing it fails.
        """
        credential = self.repository.get_by_user_id(user_id)
        if credential is None:
            logger.info("No Google OAuth credential found for user %s", user_id)
            raise GoogleCredentialNotFoundError(
                f"No Google credential connected for user {user_id}"
            )

        if credential.token_expires_at - _utc_now_naive() > TOKEN_REFRESH_SAFETY_MARGIN:
            return credential

        logger.info("Refreshing near-expiry Google access token for user %s", user_id)
        refresh_token = self.repository.encryption.decrypt(credential.refresh_token)

        google_credentials = GoogleCredentials(
            token=None,
            refresh_token=refresh_token,
            token_uri=GOOGLE_TOKEN_URI,
            client_id=settings.google_oauth_client_id,
            client_secret=settings.google_oauth_client_secret,
            scopes=credential.scopes.split(),
        )

        try:
            google_credentials.refresh(GoogleAuthRequest())
        except Exception as e:
            logger.error(
                "Failed to refresh Google access token for user %s: %s", user_id, e
            )
            raise GoogleTokenRefreshError(
                "Failed to refresh Google access token"
            ) from e

        updated_credential = self.repository.upsert(
            user_id=user_id,
            google_account_email=credential.google_account_email,
            google_account_id=credential.google_account_id,
            access_token=google_credentials.token,
            refresh_token=google_credentials.refresh_token or refresh_token,
            token_expires_at=google_credentials.expiry,
            scopes=credential.scopes,
        )
        logger.info(
            "Refreshed and persisted new Google access token for user %s", user_id
        )
        return updated_credential

    def disconnect(self, user_id: str) -> bool:
        """Revoke and delete a user's connected Google credential.

        Only this table's row is touched — no cached playlist/transcript
        data is deleted, since history has value even while disconnected.

        Args:
            user_id: The app user disconnecting their Google account.

        Returns:
            True if a credential was found and deleted, False if the user
            had none connected.
        """
        credential = self.repository.get_by_user_id(user_id)
        if credential is None:
            logger.info("No Google OAuth credential to disconnect for user %s", user_id)
            return False

        access_token = self.repository.encryption.decrypt(credential.access_token)
        try:
            response = requests.post(
                GOOGLE_REVOKE_URI,
                params={"token": access_token},
                timeout=10,
            )
            if response.status_code != 200:
                logger.warning(
                    "Google token revoke returned status %s for user %s",
                    response.status_code,
                    user_id,
                )
        except Exception as e:
            # Best-effort revoke: a failure here must not block local
            # disconnection, which is the actual acceptance criterion.
            logger.warning("Failed to revoke Google token for user %s: %s", user_id, e)

        deleted = self.repository.delete_by_user_id(user_id)
        logger.info("Disconnected Google account for user %s", user_id)
        return deleted


def get_google_auth_service(db: Session) -> GoogleAuthService:
    """Factory function for GoogleAuthService dependency injection.

    Args:
        db: SQLAlchemy database session.

    Returns:
        Configured GoogleAuthService instance.
    """
    repository = GoogleOAuthRepository(db)
    return GoogleAuthService(repository)
