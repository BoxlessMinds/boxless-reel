"""Tests for GoogleAuthService (consent URL, callback, refresh, disconnect).

Every Google-facing call (`Flow`, ID-token verification, credential refresh,
token revoke) is mocked — none of these tests reach the network.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from jose import jwt

from src.config import settings
from src.services.google_auth_service import (
    GoogleAuthService,
    GoogleAuthServiceError,
    GoogleAuthStateError,
    GoogleCredentialNotFoundError,
    GoogleTokenRefreshError,
    STATE_TOKEN_TYPE,
    _utc_now_naive,
)


@pytest.fixture
def mock_repository() -> MagicMock:
    """A bare MagicMock standing in for GoogleOAuthRepository.

    Not spec'd against the class because `encryption` is an instance
    attribute (set in `__init__`), not a class member, so a class-spec'd
    mock would reject attribute access on it.
    """
    repo = MagicMock()
    repo.encryption.decrypt.side_effect = lambda value: f"decrypted:{value}"
    repo.encryption.encrypt.side_effect = lambda value: f"encrypted:{value}"
    return repo


@pytest.fixture
def service(mock_repository: MagicMock) -> GoogleAuthService:
    """GoogleAuthService wired to the mock repository."""
    return GoogleAuthService(mock_repository)


@pytest.fixture
def fake_user() -> SimpleNamespace:
    """Minimal stand-in for a User — only `.id` is used by this service."""
    return SimpleNamespace(id="user-123")


def _make_credential(**overrides) -> SimpleNamespace:
    """Build a fake GoogleOAuthCredential-shaped object for repository mocks."""
    defaults = dict(
        user_id="user-123",
        google_account_email="user@example.com",
        google_account_id="google-sub-123",
        access_token="ciphertext-access",
        refresh_token="ciphertext-refresh",
        token_expires_at=_utc_now_naive() + timedelta(hours=1),
        scopes="https://www.googleapis.com/auth/youtube openid",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestVerifyStateToken:
    """The three bad-state cases the /callback 400 acceptance criterion needs."""

    def test_rejects_tampered_signature(self, service: GoogleAuthService) -> None:
        valid_token = jwt.encode(
            {
                "sub": "user-123",
                "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
                "type": STATE_TOKEN_TYPE,
            },
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        tampered = valid_token[:-1] + ("A" if valid_token[-1] != "A" else "B")

        with pytest.raises(GoogleAuthStateError):
            service._verify_state_token(tampered)

    def test_rejects_expired(self, service: GoogleAuthService) -> None:
        expired_token = jwt.encode(
            {
                "sub": "user-123",
                "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
                "type": STATE_TOKEN_TYPE,
            },
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )

        with pytest.raises(GoogleAuthStateError):
            service._verify_state_token(expired_token)

    def test_rejects_missing_state(self, service: GoogleAuthService) -> None:
        with pytest.raises(GoogleAuthStateError):
            service._verify_state_token(None)

        with pytest.raises(GoogleAuthStateError):
            service._verify_state_token("")

    def test_rejects_wrong_token_type(self, service: GoogleAuthService) -> None:
        wrong_type_token = jwt.encode(
            {
                "sub": "user-123",
                "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
                "type": "access",
            },
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )

        with pytest.raises(GoogleAuthStateError):
            service._verify_state_token(wrong_type_token)

    def test_accepts_valid_state_and_returns_user_id(
        self, service: GoogleAuthService
    ) -> None:
        token = service._create_state_token("user-123", "test-verifier")
        assert service._verify_state_token(token) == ("user-123", "test-verifier")


class TestBuildAuthorizationUrl:
    def test_sets_offline_and_consent(
        self, service: GoogleAuthService, fake_user: SimpleNamespace
    ) -> None:
        with patch("src.services.google_auth_service.Flow") as mock_flow_cls:
            mock_flow = MagicMock()
            mock_flow.authorization_url.return_value = (
                "https://accounts.google.com/o/oauth2/auth?mock=1",
                "state-echo",
            )
            mock_flow_cls.from_client_config.return_value = mock_flow

            url = service.build_authorization_url(fake_user)

        assert url == "https://accounts.google.com/o/oauth2/auth?mock=1"
        _, kwargs = mock_flow.authorization_url.call_args
        assert kwargs["access_type"] == "offline"
        assert kwargs["prompt"] == "consent"
        assert "state" in kwargs

        _, from_client_config_kwargs = mock_flow_cls.from_client_config.call_args
        assert (
            "https://www.googleapis.com/auth/youtube"
            in from_client_config_kwargs["scopes"]
        )


class TestHandleCallback:
    def test_rejects_bad_state_before_exchanging_code(
        self, service: GoogleAuthService, mock_repository: MagicMock
    ) -> None:
        with pytest.raises(GoogleAuthStateError):
            service.handle_callback(code="irrelevant", state="not-a-real-token")

        mock_repository.upsert.assert_not_called()

    def test_upserts_credential_on_success(
        self, service: GoogleAuthService, mock_repository: MagicMock
    ) -> None:
        state = service._create_state_token("user-123", "test-verifier")
        expiry = _utc_now_naive() + timedelta(hours=1)

        with (
            patch("src.services.google_auth_service.Flow") as mock_flow_cls,
            patch("src.services.google_auth_service.google_id_token") as mock_id_token,
        ):
            mock_flow = MagicMock()
            mock_flow.credentials = SimpleNamespace(
                token="plaintext-access-token",
                refresh_token="plaintext-refresh-token",
                expiry=expiry,
                scopes=["https://www.googleapis.com/auth/youtube", "openid"],
                id_token="fake-id-token",
            )
            mock_flow_cls.from_client_config.return_value = mock_flow
            mock_id_token.verify_oauth2_token.return_value = {
                "email": "user@example.com",
                "sub": "google-sub-123",
            }
            mock_repository.upsert.return_value = _make_credential()

            credential = service.handle_callback(code="auth-code", state=state)

        mock_flow.fetch_token.assert_called_once_with(code="auth-code")
        mock_repository.upsert.assert_called_once_with(
            user_id="user-123",
            google_account_email="user@example.com",
            google_account_id="google-sub-123",
            access_token="plaintext-access-token",
            refresh_token="plaintext-refresh-token",
            token_expires_at=expiry,
            scopes="https://www.googleapis.com/auth/youtube openid",
        )
        assert credential.google_account_email == "user@example.com"

    def test_wraps_token_exchange_failure(
        self, service: GoogleAuthService, mock_repository: MagicMock
    ) -> None:
        state = service._create_state_token("user-123", "test-verifier")

        with patch("src.services.google_auth_service.Flow") as mock_flow_cls:
            mock_flow = MagicMock()
            mock_flow.fetch_token.side_effect = Exception("network boom")
            mock_flow_cls.from_client_config.return_value = mock_flow

            with pytest.raises(GoogleAuthServiceError):
                service.handle_callback(code="auth-code", state=state)

        mock_repository.upsert.assert_not_called()


class TestGetStatus:
    """Plain read for GET /status — must never refresh or hit the network."""

    def test_returns_stored_credential_without_refreshing(
        self, service: GoogleAuthService, mock_repository: MagicMock
    ) -> None:
        stale_credential = _make_credential(
            token_expires_at=_utc_now_naive() - timedelta(minutes=1)
        )
        mock_repository.get_by_user_id.return_value = stale_credential

        result = service.get_status("user-123")

        assert result is stale_credential
        mock_repository.upsert.assert_not_called()

    def test_returns_none_when_not_connected(
        self, service: GoogleAuthService, mock_repository: MagicMock
    ) -> None:
        mock_repository.get_by_user_id.return_value = None

        assert service.get_status("user-123") is None


class TestGetValidCredential:
    def test_raises_when_no_credential(
        self, service: GoogleAuthService, mock_repository: MagicMock
    ) -> None:
        mock_repository.get_by_user_id.return_value = None

        with pytest.raises(GoogleCredentialNotFoundError):
            service.get_valid_credential("user-123")

    def test_returns_unchanged_when_not_near_expiry(
        self, service: GoogleAuthService, mock_repository: MagicMock
    ) -> None:
        credential = _make_credential(
            token_expires_at=_utc_now_naive() + timedelta(hours=1)
        )
        mock_repository.get_by_user_id.return_value = credential

        result = service.get_valid_credential("user-123")

        assert result is credential
        mock_repository.upsert.assert_not_called()

    def test_refreshes_and_persists_new_expiry(
        self, service: GoogleAuthService, mock_repository: MagicMock
    ) -> None:
        stale_credential = _make_credential(
            token_expires_at=_utc_now_naive() - timedelta(minutes=1)
        )
        mock_repository.get_by_user_id.return_value = stale_credential
        new_expiry = _utc_now_naive() + timedelta(hours=1)
        refreshed_credential = _make_credential(token_expires_at=new_expiry)
        mock_repository.upsert.return_value = refreshed_credential

        with patch(
            "src.services.google_auth_service.GoogleCredentials"
        ) as mock_credentials_cls:
            mock_google_credentials = MagicMock()
            mock_google_credentials.token = "new-plaintext-access-token"
            mock_google_credentials.refresh_token = None
            mock_google_credentials.expiry = new_expiry
            mock_credentials_cls.return_value = mock_google_credentials

            result = service.get_valid_credential("user-123")

        mock_google_credentials.refresh.assert_called_once()
        mock_repository.upsert.assert_called_once_with(
            user_id="user-123",
            google_account_email=stale_credential.google_account_email,
            google_account_id=stale_credential.google_account_id,
            access_token="new-plaintext-access-token",
            refresh_token="decrypted:ciphertext-refresh",
            token_expires_at=new_expiry,
            scopes=stale_credential.scopes,
        )
        assert result.token_expires_at == new_expiry

    def test_refresh_failure_raises_and_does_not_persist(
        self, service: GoogleAuthService, mock_repository: MagicMock
    ) -> None:
        stale_credential = _make_credential(
            token_expires_at=_utc_now_naive() - timedelta(minutes=1)
        )
        mock_repository.get_by_user_id.return_value = stale_credential

        with patch(
            "src.services.google_auth_service.GoogleCredentials"
        ) as mock_credentials_cls:
            mock_google_credentials = MagicMock()
            mock_google_credentials.refresh.side_effect = Exception("invalid_grant")
            mock_credentials_cls.return_value = mock_google_credentials

            with pytest.raises(GoogleTokenRefreshError):
                service.get_valid_credential("user-123")

        mock_repository.upsert.assert_not_called()


class TestDisconnect:
    def test_revokes_and_deletes(
        self, service: GoogleAuthService, mock_repository: MagicMock
    ) -> None:
        credential = _make_credential()
        mock_repository.get_by_user_id.return_value = credential
        mock_repository.delete_by_user_id.return_value = True

        with patch("src.services.google_auth_service.requests") as mock_requests:
            mock_requests.post.return_value = SimpleNamespace(status_code=200)

            result = service.disconnect("user-123")

        mock_requests.post.assert_called_once()
        mock_repository.delete_by_user_id.assert_called_once_with("user-123")
        assert result is True

    def test_returns_false_when_no_credential(
        self, service: GoogleAuthService, mock_repository: MagicMock
    ) -> None:
        mock_repository.get_by_user_id.return_value = None

        result = service.disconnect("user-123")

        assert result is False
        mock_repository.delete_by_user_id.assert_not_called()

    def test_revoke_failure_still_deletes_locally(
        self, service: GoogleAuthService, mock_repository: MagicMock
    ) -> None:
        credential = _make_credential()
        mock_repository.get_by_user_id.return_value = credential
        mock_repository.delete_by_user_id.return_value = True

        with patch("src.services.google_auth_service.requests") as mock_requests:
            mock_requests.post.side_effect = Exception("revoke endpoint down")

            result = service.disconnect("user-123")

        mock_repository.delete_by_user_id.assert_called_once_with("user-123")
        assert result is True
