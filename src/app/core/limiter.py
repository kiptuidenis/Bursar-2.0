from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core import config

limiter = Limiter(
    key_func=get_remote_address,
    enabled=not config.IS_TEST_MODE,
    default_limits=["120/minute"]
)
