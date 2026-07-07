import os

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

# Default to simulation mode when running tests
import sys
if "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules or os.environ.get("ALLOW_TEST_ENDPOINTS") == "1":
    os.environ["MPESA_MODE"] = "simulation"
    os.environ["INTASEND_MODE"] = "simulation"
    os.environ["RECAPTCHA_ENABLED"] = "false"



SECRET_KEY = os.environ.get("SECRET_KEY", "bursar_default_session_secret_key_change_in_prod")


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

# Google reCAPTCHA Configuration
RECAPTCHA_ENABLED = os.environ.get("RECAPTCHA_ENABLED", "true").lower() in ("true", "1", "yes")
RECAPTCHA_SITE_KEY = os.environ.get("RECAPTCHA_SITE_KEY", "")
RECAPTCHA_SECRET_KEY = os.environ.get("RECAPTCHA_SECRET_KEY", "")
try:
    RECAPTCHA_SCORE_THRESHOLD = float(os.environ.get("RECAPTCHA_SCORE_THRESHOLD", "0.5"))
except ValueError:
    RECAPTCHA_SCORE_THRESHOLD = 0.5

