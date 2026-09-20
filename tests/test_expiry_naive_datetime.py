"""Tests for expiry checks on refresh tokens and invitations.

SQLite returns DateTime columns without a timezone once a row is reloaded from
the database. These tests expire the session after creating each row so the
model reads the value back the way it does in production, instead of getting
the timezone-aware object from the session's identity map.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.invitation import Invitation
from src.models.refresh_token import RefreshToken
from src.models.user import User
from src.repositories.refresh_token_repository import RefreshTokenRepository
from src.utils.datetime_utils import as_utc


def _now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def _create_refresh_token(
    db: Session, user: User, expires_at: datetime, raw_token: str = "raw-refresh-token"
) -> str:
    """Store a refresh token, then drop cached objects so it is reloaded from SQLite."""
    RefreshTokenRepository(db).create(
        user_id=user.id, token=raw_token, expires_at=expires_at
    )
    db.expire_all()
    return raw_token


def _create_invitation(
    db: Session, inviter: User, expires_at: datetime, email: str = "invitee@example.com"
) -> str:
    """Store a pending invitation, then reload it from SQLite. Returns its token."""
    invitation = Invitation(email=email, invited_by_id=inviter.id, expires_at=expires_at)
    db.add(invitation)
    db.commit()
    token = invitation.token
    db.expire_all()
    return token


class TestAsUtc:
    """Unit tests for the as_utc helper."""

    def test_naive_value_is_treated_as_utc(self) -> None:
        naive = datetime(2030, 1, 1, 12, 0, 0)

        result = as_utc(naive)

        assert result.tzinfo == timezone.utc
        assert result.replace(tzinfo=None) == naive

    def test_aware_value_is_unchanged(self) -> None:
        aware = datetime(2030, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        assert as_utc(aware) == aware

    def test_aware_non_utc_value_keeps_its_instant(self) -> None:
        offset = timezone(timedelta(hours=5))
        aware = datetime(2030, 1, 1, 12, 0, 0, tzinfo=offset)

        assert as_utc(aware) == aware


class TestExpiryProperties:
    """Model properties must work with naive and aware stored values."""

    @pytest.mark.parametrize("make_naive", [True, False])
    def test_refresh_token_not_expired(self, make_naive: bool) -> None:
        expires_at = _now() + timedelta(days=1)
        token = RefreshToken(
            user_id="u",
            token_hash="h",
            expires_at=expires_at.replace(tzinfo=None) if make_naive else expires_at,
        )

        assert token.is_expired is False
        assert token.is_valid is True

    @pytest.mark.parametrize("make_naive", [True, False])
    def test_refresh_token_expired(self, make_naive: bool) -> None:
        expires_at = _now() - timedelta(days=1)
        token = RefreshToken(
            user_id="u",
            token_hash="h",
            expires_at=expires_at.replace(tzinfo=None) if make_naive else expires_at,
        )

        assert token.is_expired is True
        assert token.is_valid is False

    @pytest.mark.parametrize("make_naive", [True, False])
    def test_invitation_not_expired(self, make_naive: bool) -> None:
        expires_at = _now() + timedelta(days=1)
        invitation = Invitation(
            email="a@example.com",
            invited_by_id="u",
            status="pending",
            expires_at=expires_at.replace(tzinfo=None) if make_naive else expires_at,
        )

        assert invitation.is_expired is False
        assert invitation.is_valid is True

    @pytest.mark.parametrize("make_naive", [True, False])
    def test_invitation_expired(self, make_naive: bool) -> None:
        expires_at = _now() - timedelta(days=1)
        invitation = Invitation(
            email="a@example.com",
            invited_by_id="u",
            status="pending",
            expires_at=expires_at.replace(tzinfo=None) if make_naive else expires_at,
        )

        assert invitation.is_expired is True
        assert invitation.is_valid is False


class TestRefreshEndpoint:
    """POST /api/auth/refresh reads the stored expiry back from SQLite."""

    def test_refresh_with_valid_token_returns_200(
        self, client: TestClient, test_db: Session, test_user: User
    ) -> None:
        raw = _create_refresh_token(test_db, test_user, _now() + timedelta(days=7))

        response = client.post("/api/auth/refresh", json={"refresh_token": raw})

        assert response.status_code == 200
        body = response.json()
        assert body["access_token"]
        assert body["refresh_token"]
        assert body["refresh_token"] != raw

    def test_refresh_with_expired_token_returns_401(
        self, client: TestClient, test_db: Session, test_user: User
    ) -> None:
        raw = _create_refresh_token(test_db, test_user, _now() - timedelta(minutes=1))

        response = client.post("/api/auth/refresh", json={"refresh_token": raw})

        assert response.status_code == 401


class TestRegisterWithInvitation:
    """POST /api/auth/register with an invitation token."""

    def test_register_with_valid_invitation_returns_201(
        self, client: TestClient, test_db: Session, test_user: User
    ) -> None:
        token = _create_invitation(test_db, test_user, _now() + timedelta(days=7))

        response = client.post(
            "/api/auth/register",
            json={
                "email": "invitee@example.com",
                "password": "a-long-enough-password",
                "display_name": "Invitee",
                "token": token,
            },
        )

        assert response.status_code == 201
        assert response.json()["email"] == "invitee@example.com"

    def test_register_with_expired_invitation_returns_400(
        self, client: TestClient, test_db: Session, test_user: User
    ) -> None:
        token = _create_invitation(test_db, test_user, _now() - timedelta(minutes=1))

        response = client.post(
            "/api/auth/register",
            json={
                "email": "invitee@example.com",
                "password": "a-long-enough-password",
                "display_name": "Invitee",
                "token": token,
            },
        )

        assert response.status_code == 400
        assert "expired" in response.json()["detail"].lower()


class TestValidateInvitationEndpoint:
    """POST /api/invitations/validate."""

    def test_validate_valid_invitation_returns_200(
        self, client: TestClient, test_db: Session, test_user: User
    ) -> None:
        token = _create_invitation(test_db, test_user, _now() + timedelta(days=7))

        response = client.post("/api/invitations/validate", json={"token": token})

        assert response.status_code == 200
        body = response.json()
        assert body["valid"] is True
        assert body["email"] == "invitee@example.com"

    def test_validate_expired_invitation_reports_expired(
        self, client: TestClient, test_db: Session, test_user: User
    ) -> None:
        token = _create_invitation(test_db, test_user, _now() - timedelta(minutes=1))

        response = client.post("/api/invitations/validate", json={"token": token})

        assert response.status_code == 404
        assert "expired" in response.json()["detail"].lower()
