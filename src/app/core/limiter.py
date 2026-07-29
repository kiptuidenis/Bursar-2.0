from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core import config

# Explicitly configure Sliding/Moving Window Counter algorithm for smooth rate calculation
limiter = Limiter(
    key_func=get_remote_address,
    strategy="moving-window",
    enabled=not config.IS_TEST_MODE,
    default_limits=["120/minute"]
)
