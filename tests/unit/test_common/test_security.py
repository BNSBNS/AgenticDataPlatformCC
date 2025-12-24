"""
Unit tests for security utilities.

Tests password hashing, encryption, JWT handling, and other security functions.
"""

from datetime import datetime, timedelta

import pytest

from src.common.exceptions import AuthenticationError, AuthorizationError
from src.common.security import (
    APIKeyManager,
    Encryptor,
    JWTHandler,
    PasswordHasher,
    generate_correlation_id,
    mask_pii,
)


class TestPasswordHasher:
    """Test suite for PasswordHasher class."""

    def test_hash_password_returns_string(self):
        """Test that hashing returns a string."""
        hashed = PasswordHasher.hash_password("mypassword")

        assert isinstance(hashed, str)
        assert "$" in hashed  # Contains salt separator

    def test_hash_password_different_each_time(self):
        """Test that hashing same password produces different hashes (due to salt)."""
        password = "mypassword"
        hash1 = PasswordHasher.hash_password(password)
        hash2 = PasswordHasher.hash_password(password)

        assert hash1 != hash2  # Different due to different salts

    def test_verify_password_correct(self):
        """Test password verification with correct password."""
        password = "mypassword"
        hashed = PasswordHasher.hash_password(password)

        assert PasswordHasher.verify_password(hashed, password) is True

    def test_verify_password_incorrect(self):
        """Test password verification with incorrect password."""
        password = "mypassword"
        hashed = PasswordHasher.hash_password(password)

        assert PasswordHasher.verify_password(hashed, "wrongpassword") is False

    def test_verify_password_malformed_hash(self):
        """Test password verification with malformed hash."""
        assert PasswordHasher.verify_password("malformed", "password") is False


class TestEncryptor:
    """Test suite for Encryptor class."""

    def test_encrypt_returns_string(self):
        """Test that encryption returns a string."""
        encryptor = Encryptor()
        encrypted = encryptor.encrypt("secret data")

        assert isinstance(encrypted, str)

    def test_encrypt_decrypt_roundtrip(self):
        """Test that encryption and decryption work correctly."""
        encryptor = Encryptor()
        original = "secret data"

        encrypted = encryptor.encrypt(original)
        decrypted = encryptor.decrypt(encrypted)

        assert decrypted == original

    def test_encrypted_data_different_each_time(self):
        """Test that encrypting same data produces different ciphertext."""
        encryptor = Encryptor()
        data = "secret"

        encrypted1 = encryptor.encrypt(data)
        encrypted2 = encryptor.encrypt(data)

        # Note: Fernet includes timestamp, so ciphertext will be different
        assert encrypted1 != encrypted2

    def test_decrypt_with_different_key_fails(self):
        """Test that decryption with wrong key fails."""
        encryptor1 = Encryptor()
        encryptor2 = Encryptor()  # Different key

        encrypted = encryptor1.encrypt("secret")

        with pytest.raises(Exception):  # Fernet raises cryptography.fernet.InvalidToken
            encryptor2.decrypt(encrypted)


class TestJWTHandler:
    """Test suite for JWTHandler class."""

    def test_create_access_token(self):
        """Test JWT token creation."""
        handler = JWTHandler()
        token = handler.create_access_token("user@example.com")

        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_access_token_with_claims(self):
        """Test JWT token creation with additional claims."""
        handler = JWTHandler()
        additional_claims = {"role": "admin", "permissions": ["read", "write"]}

        token = handler.create_access_token("user@example.com", additional_claims)
        payload = handler.decode_token(token)

        assert payload["role"] == "admin"
        assert payload["permissions"] == ["read", "write"]

    def test_create_access_token_with_custom_expiry(self):
        """Test JWT token creation with custom expiration."""
        handler = JWTHandler()
        expires_delta = timedelta(minutes=5)

        token = handler.create_access_token(
            "user@example.com", expires_delta=expires_delta
        )
        payload = handler.decode_token(token)

        exp_datetime = datetime.fromtimestamp(payload["exp"])
        iat_datetime = datetime.fromtimestamp(payload["iat"])
        delta = exp_datetime - iat_datetime

        # Should be approximately 5 minutes (allow 1 second tolerance)
        assert 299 <= delta.total_seconds() <= 301

    def test_decode_token(self):
        """Test JWT token decoding."""
        handler = JWTHandler()
        subject = "user@example.com"

        token = handler.create_access_token(subject)
        payload = handler.decode_token(token)

        assert payload["sub"] == subject
        assert "exp" in payload
        assert "iat" in payload
        assert payload["type"] == "access"

    def test_decode_invalid_token(self):
        """Test decoding invalid token raises error."""
        handler = JWTHandler()

        with pytest.raises(AuthenticationError):
            handler.decode_token("invalid.token.here")

    def test_validate_token_success(self):
        """Test successful token validation."""
        handler = JWTHandler()
        token = handler.create_access_token("user@example.com")

        payload = handler.validate_token(token)

        assert payload["sub"] == "user@example.com"

    def test_validate_token_with_required_claims(self):
        """Test token validation with required claims."""
        handler = JWTHandler()
        token = handler.create_access_token(
            "user@example.com", {"role": "admin", "org": "acme"}
        )

        payload = handler.validate_token(token, required_claims=["role", "org"])

        assert payload["role"] == "admin"
        assert payload["org"] == "acme"

    def test_validate_token_missing_required_claims(self):
        """Test token validation fails with missing claims."""
        handler = JWTHandler()
        token = handler.create_access_token("user@example.com")

        with pytest.raises(AuthorizationError, match="Missing required claims"):
            handler.validate_token(token, required_claims=["role", "permissions"])


class TestAPIKeyManager:
    """Test suite for APIKeyManager class."""

    def test_generate_api_key(self):
        """Test API key generation."""
        key = APIKeyManager.generate_api_key()

        assert isinstance(key, str)
        assert key.startswith("dp_")
        assert len(key) > 10

    def test_generate_api_key_custom_prefix(self):
        """Test API key generation with custom prefix."""
        key = APIKeyManager.generate_api_key(prefix="test")

        assert key.startswith("test_")

    def test_hash_api_key(self):
        """Test API key hashing."""
        key = "dp_test_key_12345"
        hashed = APIKeyManager.hash_api_key(key)

        assert isinstance(hashed, str)
        assert hashed != key
        assert len(hashed) == 64  # SHA-256 hex digest length

    def test_verify_api_key_correct(self):
        """Test API key verification with correct key."""
        key = APIKeyManager.generate_api_key()
        hashed = APIKeyManager.hash_api_key(key)

        assert APIKeyManager.verify_api_key(hashed, key) is True

    def test_verify_api_key_incorrect(self):
        """Test API key verification with incorrect key."""
        key = APIKeyManager.generate_api_key()
        hashed = APIKeyManager.hash_api_key(key)
        wrong_key = APIKeyManager.generate_api_key()

        assert APIKeyManager.verify_api_key(hashed, wrong_key) is False


class TestPIIMasking:
    """Test suite for PII masking functions."""

    def test_mask_email(self):
        """Test email masking."""
        email = "john.doe@example.com"
        masked = mask_pii(email)

        assert masked == "joh***@e***"
        assert "@" in masked
        assert "john.doe" not in masked
        assert "example.com" not in masked

    def test_mask_short_email(self):
        """Test masking short email."""
        email = "a@b.c"
        masked = mask_pii(email)

        assert "@" in masked
        assert "***" in masked

    def test_mask_general_data(self):
        """Test general data masking."""
        data = "1234567890"
        masked = mask_pii(data, visible_chars=4)

        assert masked == "1234***7890"
        assert "56" not in masked

    def test_mask_short_data(self):
        """Test masking data shorter than visible chars."""
        data = "abc"
        masked = mask_pii(data, visible_chars=3)

        assert masked == "***"

    def test_mask_custom_char(self):
        """Test masking with custom mask character."""
        data = "sensitive"
        masked = mask_pii(data, mask_char="X", visible_chars=2)

        assert masked == "seXXXve"


class TestCorrelationID:
    """Test suite for correlation ID generation."""

    def test_generate_correlation_id(self):
        """Test correlation ID generation."""
        corr_id = generate_correlation_id()

        assert isinstance(corr_id, str)
        assert len(corr_id) == 32  # hex string of 16 bytes

    def test_generate_correlation_id_unique(self):
        """Test that correlation IDs are unique."""
        ids = {generate_correlation_id() for _ in range(100)}

        assert len(ids) == 100  # All unique
