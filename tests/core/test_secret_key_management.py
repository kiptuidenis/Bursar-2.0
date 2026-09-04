import os
import pytest
from pydantic import SecretStr

from app.core.security import SessionManager
from app.core.config import parse_secret_key, parse_fallback_secret_keys, validate_environment_secret_keys


def test_parse_secret_key_valid():
    """Test valid secret keys pass validation and return bytes."""
    valid_key = "a" * 32
    result = parse_secret_key(valid_key)
    assert isinstance(result, bytes)
    assert result == valid_key.encode("utf-8")


def test_parse_secret_key_hex_decoding():
    """Test 64-char hex strings are converted to 32 raw bytes."""
    hex_key = "41" * 32  # 'A' * 32 in hex
    result = parse_secret_key(hex_key)
    assert isinstance(result, bytes)
    assert result == b"A" * 32


def test_parse_secret_key_invalid():
    """Test invalid or weak secret keys raise ValueError."""
    invalid_keys = [
        "",
        "   ",
        "bursar_default_session_secret_key_change_in_prod",
        "your_secret_key_here",
        "change_me",
        "too_short",
        "   spaces_around_short   ",
    ]
    for key in invalid_keys:
        with pytest.raises(ValueError):
            parse_secret_key(key)


def test_parse_fallback_secret_keys_formatting_and_limit():
    """Test parsing fallback keys strips whitespace, ignores empties, and caps at MAX_FALLBACK_KEYS=3."""
    raw_fallbacks = "  key1_long_enough_string_32_chars_long  ,   , key2_long_enough_string_32_chars_long, key3_long_enough_string_32_chars_long, key4_ignored_excess_key_32_chars "
    parsed = parse_fallback_secret_keys(raw_fallbacks, max_fallbacks=3)
    assert len(parsed) == 3
    assert parsed[0] == b"key1_long_enough_string_32_chars_long"
    assert parsed[1] == b"key2_long_enough_string_32_chars_long"
    assert parsed[2] == b"key3_long_enough_string_32_chars_long"


def test_validate_environment_secret_keys_non_test_missing(monkeypatch):
    """Test startup fails with informative RuntimeError when SECRET_KEY is missing in non-test mode."""
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    
    with pytest.raises(RuntimeError) as exc_info:
        validate_environment_secret_keys(is_test_mode=False)
        
    assert "SECRET_KEY environment variable is not configured" in str(exc_info.value)
    assert "secrets.token_hex(32)" in str(exc_info.value)


def test_secret_rotation_verification():
    """Test session validation succeeds with fallback key when primary key rotates."""
    primary_key = "primary_secret_key_32_characters_long"
    old_key = "old_secret_key_32_characters_long"

    # Create session with old key
    old_manager = SessionManager(secret_key=old_key)
    token = old_manager.create_session(user_id=100, expires_in_seconds=3600)

    # New manager initialized after rotation (old_key passed in fallback_secret_keys)
    new_manager = SessionManager(
        secret_key=primary_key,
        fallback_secret_keys=[old_key]
    )

    # Validation must succeed using fallback key
    user_id = new_manager.validate_session(token)
    assert user_id == 100

    # New session created by new manager should be signed with primary key
    new_token = new_manager.create_session(user_id=100, expires_in_seconds=3600)
    
    # Old manager (without new primary key) cannot validate new token
    assert old_manager.validate_session(new_token) is None


def test_pydantic_secretstr_redaction():
    """Test SecretStr masks secret key in string representation."""
    secret = SecretStr("super_secret_value_32_chars_long")
    assert str(secret) == "**********"
    assert repr(secret) == "SecretStr('**********')"
    assert secret.get_secret_value() == "super_secret_value_32_chars_long"
