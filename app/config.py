import os

def load_dotenv(filepath=".env"):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, value = line.split("=", 1)
                        os.environ[key.strip()] = value.strip().strip('"').strip("'")
        except Exception:
            pass

# Trigger loading .env from project root
load_dotenv(".env")

# Default to simulation mode when running tests
if "PYTEST_CURRENT_TEST" in os.environ:
    os.environ.setdefault("MPESA_MODE", "simulation")

# Load Configuration Properties
MPESA_MODE = os.environ.get("MPESA_MODE", "sandbox").lower()
MPESA_CONSUMER_KEY = os.environ.get("MPESA_CONSUMER_KEY", "")
MPESA_CONSUMER_SECRET = os.environ.get("MPESA_CONSUMER_SECRET", "")
MPESA_SHORTCODE = os.environ.get("MPESA_SHORTCODE", "")
MPESA_INITIATOR_NAME = os.environ.get("MPESA_INITIATOR_NAME", "")
MPESA_INITIATOR_PASSWORD = os.environ.get("MPESA_INITIATOR_PASSWORD", "")
MPESA_B2C_RESULT_URL = os.environ.get("MPESA_B2C_RESULT_URL", "")
MPESA_B2C_TIMEOUT_URL = os.environ.get("MPESA_B2C_TIMEOUT_URL", "")
