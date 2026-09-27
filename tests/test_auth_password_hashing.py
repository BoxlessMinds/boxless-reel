"""Tests that password hashing works for new and existing users.

These call the real hasher (passlib with bcrypt), with no mocks, so they
fail if a bcrypt upgrade stops passlib from hashing or verifying.
"""

from src.services.auth_service import AuthService

# A throwaway password and the hash that bcrypt 4.0.1 produced for it.
# It stands in for the stored hash of a user who registered before any upgrade.
SAMPLE_PASSWORD = "sample-password-for-tests"
SAMPLE_HASH_FROM_BCRYPT_4_0_1 = "$2b$12$/6yJ6rKhJuyAhoyOSBbnf.NRhYhgaRjt9dCOTESgwExddpbmXrAb2"


class TestPasswordHashing:
    """Hashing and verifying passwords through AuthService."""

    def test_hash_then_verify_round_trip(self) -> None:
        """A freshly hashed password verifies, and a wrong one does not."""
        password_hash = AuthService.hash_password(SAMPLE_PASSWORD)

        assert password_hash.startswith("$2b$")
        assert AuthService.verify_password(SAMPLE_PASSWORD, password_hash) is True
        assert AuthService.verify_password("wrong-password", password_hash) is False

    def test_hash_created_under_bcrypt_4_0_1_still_verifies(self) -> None:
        """A hash stored by an older bcrypt still lets that user log in."""
        assert AuthService.verify_password(SAMPLE_PASSWORD, SAMPLE_HASH_FROM_BCRYPT_4_0_1) is True

    def test_hash_created_under_bcrypt_4_0_1_rejects_wrong_password(self) -> None:
        """An older stored hash still rejects the wrong password."""
        assert AuthService.verify_password("wrong-password", SAMPLE_HASH_FROM_BCRYPT_4_0_1) is False
