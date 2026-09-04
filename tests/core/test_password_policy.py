import pytest
from app.core.password import validate_password_strength

def test_password_under_8_chars_rejected():
    err = validate_password_strength("Pass1!")
    assert err is not None
    assert "at least 8 characters" in err

def test_password_missing_uppercase_rejected():
    err = validate_password_strength("password123!")
    assert err is not None
    assert "uppercase letter" in err

def test_password_missing_lowercase_rejected():
    err = validate_password_strength("PASSWORD123!")
    assert err is not None
    assert "lowercase letter" in err

def test_password_missing_digit_rejected():
    err = validate_password_strength("Password!")
    assert err is not None
    assert "numeric digit" in err

def test_password_missing_symbol_rejected():
    err = validate_password_strength("Password123")
    assert err is not None
    assert "special symbol" in err

def test_password_contains_phone_number_rejected():
    err = validate_password_strength("StrongP@ss712345678", user_context="254712345678")
    assert err is not None
    assert "phone number" in err

def test_password_contains_breached_term_rejected():
    err = validate_password_strength("BursarSecure2026!")
    assert err is not None
    assert "common weak pattern" in err

def test_password_repetition_rejected():
    err = validate_password_strength("Paaaaassword123!")
    assert err is not None
    assert "repeated consecutive characters" in err

def test_valid_strong_passwords_accepted():
    assert validate_password_strength("Burs@rSecur32026!") is None
    assert validate_password_strength("Str0ng!P@ssw0rd") is None
    assert validate_password_strength("K3ny@Fintech#2026") is None
