import os
import sys


def load_dotenv(filepath=".env"):
    resolved_path = filepath
    if not os.path.isabs(filepath) and not os.path.exists(filepath):
        try:
            # config.py is in src/app/core/config.py, project root is 3 levels up
            root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
            possible_path = os.path.join(root_dir, filepath)
            if os.path.exists(possible_path):
                resolved_path = possible_path
        except Exception:
            pass

    if os.path.exists(resolved_path):
        try:
            with open(resolved_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, value = line.split("=", 1)
                        k = key.strip()
                        if k not in os.environ:
                            os.environ[k] = value.strip().strip('"').strip("'")
        except Exception:
            pass


# Trigger loading .env from project root
load_dotenv(".env")

import re
from typing import List, Union
from pydantic import SecretStr

INSECURE_SECRET_PLACEHOLDERS = {
    "bursar_default_session_secret_key_change_in_prod",
    "your_secret_key_here",
    "change_me",
    "secret",
}

ORIGIN_REGEX = re.compile(r"^https?://[a-zA-Z0-9.-]+(?::\d+)?$")
DEFAULT_DEV_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:3000",
]


def parse_allowed_origins(
    raw_origins: str, 
    is_test_mode: bool = False, 
    is_dev_mode: bool = True
) -> List[str]:
    """
    Parses, validates, and normalizes allowed CORS origins.
    Rejects wildcards '*' when credentials are enabled.
    In production mode (non-dev, non-test), missing ALLOWED_ORIGINS raises RuntimeError.
    """
    raw_clean = (raw_origins or "").strip()

    if not raw_clean:
        if is_test_mode or is_dev_mode:
            return list(DEFAULT_DEV_ORIGINS)
        raise RuntimeError(
            "CRITICAL CORS CONFIGURATION ERROR: ALLOWED_ORIGINS environment variable must be explicitly defined in production mode.\n"
            "Example: ALLOWED_ORIGINS=https://bursar.co.ke,https://app.bursar.co.ke\n"
        )

    parsed = []
    items = raw_clean.split(",")
    for item in items:
        cleaned = item.strip().rstrip("/")
        if not cleaned:
            continue
        if cleaned == "*":
            raise ValueError(
                "CRITICAL CORS SECURITY ERROR: Wildcard '*' origin is forbidden when allow_credentials=True. "
                "Specify explicit allowed origins."
            )
        if not ORIGIN_REGEX.match(cleaned):
            raise ValueError(
                f"Invalid CORS origin format: '{cleaned}'. Origin must include scheme (http:// or https://), "
                "valid host/domain/IP, optional port, and no path segments."
            )
        if cleaned not in parsed:
            parsed.append(cleaned)

    if not parsed:
        if is_test_mode or is_dev_mode:
            return list(DEFAULT_DEV_ORIGINS)
        raise RuntimeError(
            "CRITICAL CORS CONFIGURATION ERROR: ALLOWED_ORIGINS environment variable must be explicitly defined in production mode."
        )

    return parsed


def parse_secret_key(key_input: Union[str, SecretStr, bytes]) -> bytes:
    """Validate secret key strength and return raw bytes representation."""
    if isinstance(key_input, SecretStr):
        raw_val = key_input.get_secret_value()
    elif isinstance(key_input, bytes):
        raw_val = key_input.decode("utf-8")
    else:
        raw_val = str(key_input or "")

    cleaned = raw_val.strip().strip('"').strip("'")
    if not cleaned:
        raise ValueError("Secret key cannot be empty or contain only whitespace.")

    if cleaned.lower() in INSECURE_SECRET_PLACEHOLDERS:
        raise ValueError("Insecure default or placeholder secret key detected.")

    if len(cleaned) < 32:
        raise ValueError(f"Secret key must be at least 32 characters long (got {len(cleaned)}).")

    # Attempt hex decoding if 64 hex characters (e.g. from secrets.token_hex(32))
    if len(cleaned) == 64:
        try:
            return bytes.fromhex(cleaned)
        except ValueError:
            pass

    return cleaned.encode("utf-8")


def parse_fallback_secret_keys(raw_fallbacks: str, max_fallbacks: int = 3) -> List[bytes]:
    """Parse comma-separated fallback secret keys, stripping whitespace and capping at max_fallbacks."""
    if not raw_fallbacks or not raw_fallbacks.strip():
        return []

    fallbacks = []
    items = raw_fallbacks.split(",")
    for item in items:
        item_clean = item.strip()
        if not item_clean:
            continue
        try:
            parsed_key = parse_secret_key(item_clean)
            fallbacks.append(parsed_key)
        except ValueError:
            continue
        if len(fallbacks) >= max_fallbacks:
            break
    return fallbacks


def validate_environment_secret_keys(is_test_mode: bool = False) -> SecretStr:
    """Validate environment SECRET_KEY. In non-test mode, raises RuntimeError if invalid."""
    env_secret = os.environ.get("SECRET_KEY", "").strip()

    if is_test_mode and not env_secret:
        # Fixed deterministic fallback for test environment only
        return SecretStr("test_environment_secret_key_32_chars_minimum_len")

    try:
        parse_secret_key(env_secret)
        return SecretStr(env_secret)
    except ValueError as e:
        if is_test_mode:
            return SecretStr("test_environment_secret_key_32_chars_minimum_len")
        raise RuntimeError(
            "CRITICAL SECURITY CONFIGURATION ERROR: SECRET_KEY environment variable is not configured correctly.\n"
            f"Details: {e}\n"
            "To fix this, set a strong SECRET_KEY in your environment or .env file.\n"
            "You can generate a cryptographically secure key by running:\n"
            "  python -c \"import secrets; print(secrets.token_hex(32))\"\n"
        ) from e


IS_TEST_MODE = "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules or os.environ.get("ALLOW_TEST_ENDPOINTS") == "1"

if IS_TEST_MODE:
    os.environ["MPESA_MODE"] = "simulation"
    os.environ["INTASEND_MODE"] = "simulation"
    os.environ["RECAPTCHA_ENABLED"] = "false"

SECRET_KEY: SecretStr = validate_environment_secret_keys(is_test_mode=IS_TEST_MODE)
FALLBACK_SECRET_KEYS: List[bytes] = parse_fallback_secret_keys(os.environ.get("OLD_SECRET_KEYS", ""), max_fallbacks=3)

APP_ENV = os.environ.get("APP_ENV", "development").lower()
IS_DEV_MODE = APP_ENV in ("development", "dev", "local")

ALLOWED_ORIGINS: List[str] = parse_allowed_origins(
    os.environ.get("ALLOWED_ORIGINS", ""),
    is_test_mode=IS_TEST_MODE,
    is_dev_mode=IS_DEV_MODE
)
CORS_ALLOWED_METHODS: List[str] = ["GET", "POST", "DELETE", "OPTIONS"]
CORS_ALLOWED_HEADERS: List[str] = ["Content-Type", "Authorization", "Accept", "X-Requested-With", "X-Background-Poll"]
CORS_MAX_AGE: int = 600

_cookie_secure_env = os.environ.get("SESSION_COOKIE_SECURE", "").strip().lower()
if not IS_DEV_MODE and not IS_TEST_MODE:
    # Production: always enforce True regardless of env setting
    SESSION_COOKIE_SECURE: bool = True
elif _cookie_secure_env in ("true", "1", "yes"):
    # Dev/test: only enable if explicitly opted in
    SESSION_COOKIE_SECURE = True
else:
    # Default for dev/test: False (HTTP TestClient needs cookies without Secure flag)
    SESSION_COOKIE_SECURE = False







# Load Configuration Properties
MPESA_MODE = os.environ.get("MPESA_MODE", "sandbox").lower()
MPESA_CONSUMER_KEY = os.environ.get("MPESA_CONSUMER_KEY", "")
MPESA_CONSUMER_SECRET = os.environ.get("MPESA_CONSUMER_SECRET", "")
MPESA_SHORTCODE = os.environ.get("MPESA_SHORTCODE", "")
MPESA_INITIATOR_NAME = os.environ.get("MPESA_INITIATOR_NAME", "")
MPESA_INITIATOR_PASSWORD = os.environ.get("MPESA_INITIATOR_PASSWORD", "")
MPESA_B2C_RESULT_URL = os.environ.get("MPESA_B2C_RESULT_URL", "")
MPESA_B2C_TIMEOUT_URL = os.environ.get("MPESA_B2C_TIMEOUT_URL", "")

# Lipa Na M-Pesa Online (STK Push) Settings
MPESA_LNM_SHORTCODE = os.environ.get("MPESA_LNM_SHORTCODE", "174379")
MPESA_LNM_PASSKEY = os.environ.get("MPESA_LNM_PASSKEY", "bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919")
MPESA_STK_CALLBACK_URL = os.environ.get("MPESA_STK_CALLBACK_URL", "")

# Payment Gateway Routing Config
PAYMENT_PROVIDER = os.environ.get("PAYMENT_PROVIDER", "intasend").lower()


# IntaSend Gateway Settings
INTASEND_MODE = os.environ.get("INTASEND_MODE", "simulation").lower()
INTASEND_SECRET_KEY = os.environ.get("INTASEND_SECRET_KEY", "")
INTASEND_PUBLISHABLE_KEY = os.environ.get("INTASEND_PUBLISHABLE_KEY", "")
INTASEND_WEBHOOK_CHALLENGE = os.environ.get("INTASEND_WEBHOOK_CHALLENGE", "")

# Google reCAPTCHA Configuration
RECAPTCHA_ENABLED = os.environ.get("RECAPTCHA_ENABLED", "true").lower() in ("true", "1", "yes")
RECAPTCHA_SITE_KEY = os.environ.get("RECAPTCHA_SITE_KEY", "")
RECAPTCHA_SECRET_KEY = os.environ.get("RECAPTCHA_SECRET_KEY", "")


def validate_callback_secret_token(is_test_mode: bool = False, is_dev_mode: bool = True) -> str:
    """Validate environment CALLBACK_SECRET_TOKEN. In production mode, raises RuntimeError if missing or under 32 chars."""
    raw_secret = os.environ.get("CALLBACK_SECRET_TOKEN", "").strip()

    if not raw_secret:
        if is_test_mode or is_dev_mode:
            return "ci_test_callback_secret_token_32chars_minimum"
        raise RuntimeError(
            "CRITICAL SECURITY CONFIGURATION ERROR: CALLBACK_SECRET_TOKEN environment variable must be explicitly defined in production mode.\n"
            "To fix this, set a strong CALLBACK_SECRET_TOKEN in your environment or .env file (minimum 32 characters).\n"
        )

    if len(raw_secret) < 32:
        if is_test_mode or is_dev_mode:
            return raw_secret
        raise RuntimeError(
            f"CRITICAL SECURITY CONFIGURATION ERROR: CALLBACK_SECRET_TOKEN must be at least 32 characters long in production mode (got {len(raw_secret)})."
        )

    return raw_secret


CALLBACK_SECRET_TOKEN: str = validate_callback_secret_token(is_test_mode=IS_TEST_MODE, is_dev_mode=IS_DEV_MODE)

_raw_allowed_ips = os.environ.get("ALLOWED_CALLBACK_IPS", "").strip()
ALLOWED_CALLBACK_IPS: List[str] = [_ip.strip() for _ip in _raw_allowed_ips.split(",") if _ip.strip()] if _raw_allowed_ips else []

try:
    RECAPTCHA_SCORE_THRESHOLD = float(os.environ.get("RECAPTCHA_SCORE_THRESHOLD", "0.5"))
except ValueError:
    RECAPTCHA_SCORE_THRESHOLD = 0.5

