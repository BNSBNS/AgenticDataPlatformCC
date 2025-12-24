"""
Security Utilities

Common security functions including hashing, encryption, JWT handling.
"""

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet
from jose import JWTError, jwt

from src.common.config import get_config
from src.common.exceptions import AuthenticationError, AuthorizationError


class PasswordHasher:
    """Password hashing and verification."""

    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hash a password using SHA-256 with salt.

        Args:
            password: Plain text password

        Returns:
            Hashed password with salt
        """
        salt = secrets.token_hex(32)
        pwdhash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
        return f"{salt}${pwdhash.hex()}"

    @staticmethod
    def verify_password(stored_password: str, provided_password: str) -> bool:
        """
        Verify a password against the stored hash.

        Args:
            stored_password: Stored password hash
            provided_password: Password provided by user

        Returns:
            True if password matches, False otherwise
        """
        try:
            salt, pwdhash = stored_password.split("$")
            pwdhash_check = hashlib.pbkdf2_hmac(
                "sha256", provided_password.encode("utf-8"), salt.encode("utf-8"), 100000
            )
            return pwdhash == pwdhash_check.hex()
        except Exception:
            return False


class Encryptor:
    """Data encryption and decryption using Fernet (AES-256)."""

    def __init__(self, key: Optional[str] = None):
        """
        Initialize encryptor.

        Args:
            key: Encryption key (base64 encoded), if None uses config
        """
        config = get_config()
        if key is None:
            # In production, this should come from a secure key management service
            key = config.encryption_key

        # Generate proper Fernet key if needed
        if not key or key == "your-encryption-key-change-this-in-production":
            key = Fernet.generate_key().decode()

        self.cipher = Fernet(key.encode())

    def encrypt(self, data: str) -> str:
        """
        Encrypt data.

        Args:
            data: Plain text data

        Returns:
            Encrypted data (base64 encoded)
        """
        encrypted = self.cipher.encrypt(data.encode())
        return encrypted.decode()

    def decrypt(self, encrypted_data: str) -> str:
        """
        Decrypt data.

        Args:
            encrypted_data: Encrypted data (base64 encoded)

        Returns:
            Decrypted plain text data
        """
        decrypted = self.cipher.decrypt(encrypted_data.encode())
        return decrypted.decode()


class JWTHandler:
    """JWT token creation and validation."""

    def __init__(self):
        """Initialize JWT handler with config."""
        config = get_config()
        self.secret_key = config.jwt_secret_key
        self.algorithm = config.jwt_algorithm
        self.expiration_minutes = config.jwt_expiration_minutes

    def create_access_token(
        self,
        subject: str,
        additional_claims: Optional[Dict[str, Any]] = None,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """
        Create a JWT access token.

        Args:
            subject: Subject of the token (usually user ID or email)
            additional_claims: Additional claims to include in token
            expires_delta: Custom expiration time

        Returns:
            Encoded JWT token
        """
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=self.expiration_minutes)

        claims = {
            "sub": subject,
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "access",
        }

        if additional_claims:
            claims.update(additional_claims)

        encoded_jwt = jwt.encode(claims, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def decode_token(self, token: str) -> Dict[str, Any]:
        """
        Decode and validate a JWT token.

        Args:
            token: JWT token to decode

        Returns:
            Decoded token claims

        Raises:
            AuthenticationError: If token is invalid or expired
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except JWTError as e:
            raise AuthenticationError(f"Invalid token: {str(e)}")

    def validate_token(self, token: str, required_claims: Optional[list] = None) -> Dict[str, Any]:
        """
        Validate a JWT token and check for required claims.

        Args:
            token: JWT token to validate
            required_claims: List of required claim keys

        Returns:
            Decoded token claims

        Raises:
            AuthenticationError: If token is invalid
            AuthorizationError: If required claims are missing
        """
        payload = self.decode_token(token)

        if required_claims:
            missing_claims = [claim for claim in required_claims if claim not in payload]
            if missing_claims:
                raise AuthorizationError(
                    f"Missing required claims: {', '.join(missing_claims)}"
                )

        return payload


class APIKeyManager:
    """API key generation and validation."""

    @staticmethod
    def generate_api_key(prefix: str = "dp") -> str:
        """
        Generate a secure API key.

        Args:
            prefix: Prefix for the API key

        Returns:
            Generated API key
        """
        random_part = secrets.token_urlsafe(32)
        return f"{prefix}_{random_part}"

    @staticmethod
    def hash_api_key(api_key: str) -> str:
        """
        Hash an API key for storage.

        Args:
            api_key: API key to hash

        Returns:
            Hashed API key
        """
        return hashlib.sha256(api_key.encode()).hexdigest()

    @staticmethod
    def verify_api_key(stored_hash: str, provided_key: str) -> bool:
        """
        Verify an API key against stored hash.

        Args:
            stored_hash: Stored API key hash
            provided_key: API key provided by user

        Returns:
            True if key matches, False otherwise
        """
        provided_hash = APIKeyManager.hash_api_key(provided_key)
        return secrets.compare_digest(stored_hash, provided_hash)


def mask_pii(data: str, mask_char: str = "*", visible_chars: int = 3) -> str:
    """
    Mask PII data for logging/display.

    Args:
        data: Data to mask
        mask_char: Character to use for masking
        visible_chars: Number of characters to leave visible at start/end

    Returns:
        Masked data

    Example:
        mask_pii("john.doe@example.com") -> "joh***@e***"
        mask_pii("1234567890", visible_chars=4) -> "1234***7890"
    """
    if len(data) <= visible_chars * 2:
        return mask_char * len(data)

    if "@" in data:  # Email masking
        username, domain = data.split("@")
        masked_username = username[:visible_chars] + mask_char * 3
        masked_domain = domain[0] + mask_char * 3
        return f"{masked_username}@{masked_domain}"

    # General masking
    start = data[:visible_chars]
    end = data[-visible_chars:]
    return f"{start}{mask_char * 3}{end}"


def sanitize_sql(sql: str) -> str:
    """
    Basic SQL injection prevention (NOT a complete solution).
    For production, use parameterized queries.

    Args:
        sql: SQL string to sanitize

    Returns:
        Sanitized SQL string
    """
    # Remove common SQL injection patterns
    dangerous_patterns = [
        ";--",
        "';",
        "--",
        "/*",
        "*/",
        "xp_",
        "sp_",
        "exec(",
        "execute(",
    ]

    sanitized = sql
    for pattern in dangerous_patterns:
        sanitized = sanitized.replace(pattern, "")

    return sanitized


def generate_correlation_id() -> str:
    """
    Generate a correlation ID for request tracking.

    Returns:
        Correlation ID
    """
    return secrets.token_hex(16)
