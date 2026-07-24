import re
from typing import Optional

# Top breached/common dictionary roots (lowercase)
COMMON_BREACHED_PATTERNS = {
    "password", "bursar", "admin", "qwerty", "safaricom",
    "123456", "12345678", "123456789", "welcome", "letmein",
    "monkey", "dragon", "master", "access", "shadow"
}

def validate_password_strength(password: str, user_context: Optional[str] = None) -> Optional[str]:
    """
    Validates password strength according to NIST SP 800-63B and OWASP ASVS 4.0 guidelines:
    - Minimum length 8 characters
    - Must contain uppercase, lowercase, digit, and special symbol
    - Must not contain user context (e.g., phone number)
    - Must not match common breached dictionary roots
    - Must not contain 4+ repeated consecutive characters
    
    Returns an error message string if invalid, or None if valid.
    """
    if not password:
        return "Password is required."
        
    if len(password) < 8:
        return "Password must be at least 8 characters long."

    if len(password) > 128:
        return "Password cannot exceed 128 characters."

    # Character set requirements
    if not re.search(r"[A-Z]", password):
        return "Password must contain at least one uppercase letter (A-Z)."

    if not re.search(r"[a-z]", password):
        return "Password must contain at least one lowercase letter (a-z)."

    if not re.search(r"[0-9]", password):
        return "Password must contain at least one numeric digit (0-9)."

    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?]", password):
        return "Password must contain at least one special symbol (e.g. @, $, !, %, *, #, ?, &)."

    # Repetition check (4+ identical consecutive chars)
    if re.search(r"(.)\1{3,}", password):
        return "Password contains too many repeated consecutive characters."

    # Contextual check against user phone number
    if user_context:
        clean_context = re.sub(r"\D", "", user_context)
        if len(clean_context) >= 6:
            # Check last 6, 7, 9 digits or full string
            suffix_6 = clean_context[-6:]
            if suffix_6 in password or clean_context in password:
                return "Password must not contain your phone number or phone number sequence."

    # Common breached words check
    lowered = password.lower()
    for root in COMMON_BREACHED_PATTERNS:
        if root in lowered:
            return f"Password contains a common weak pattern ('{root}'). Please choose a more unique password."

    return None
