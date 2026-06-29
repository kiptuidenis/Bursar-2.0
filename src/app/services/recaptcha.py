import logging
from typing import Optional
import httpx
from app.core import config

logger = logging.getLogger(__name__)

GOOGLE_VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"

def verify_recaptcha_token(token: Optional[str], client_ip: Optional[str] = None) -> bool:
    """
    Verifies a reCAPTCHA response token against Google's siteverify API.
    Returns True if verification succeeds (or if RECAPTCHA_ENABLED is False / credentials missing).
    """
    if not config.RECAPTCHA_ENABLED:
        logger.info("reCAPTCHA validation skipped: RECAPTCHA_ENABLED is false.")
        return True

    # If secret key is not set or placeholder, bypass for local testing convenience
    if not config.RECAPTCHA_SECRET_KEY or config.RECAPTCHA_SECRET_KEY == "your_recaptcha_secret_key_here":
        logger.warning("reCAPTCHA secret key is not configured. Skipping verification.")
        return True

    if not token:
        logger.warning("reCAPTCHA validation failed: No token provided.")
        return False

    payload = {
        "secret": config.RECAPTCHA_SECRET_KEY,
        "response": token
    }
    if client_ip:
        payload["remoteip"] = client_ip

    try:
        response = httpx.post(GOOGLE_VERIFY_URL, data=payload, timeout=5.0)
        if response.status_code != 200:
            logger.error(f"Google siteverify HTTP error: {response.status_code}")
            return False

        data = response.json()
        success = data.get("success", False)
        if not success:
            logger.warning(f"reCAPTCHA verification failed. Error codes: {data.get('error-codes', [])}")
            return False

        # Check score for reCAPTCHA v3 (if score field is returned by Google)
        if "score" in data:
            score = float(data.get("score", 0.0))
            if score < config.RECAPTCHA_SCORE_THRESHOLD:
                logger.warning(f"reCAPTCHA score {score} is below threshold {config.RECAPTCHA_SCORE_THRESHOLD}")
                return False

        return True
    except Exception as e:
        logger.error(f"Exception during reCAPTCHA verification: {e}")
        return False
