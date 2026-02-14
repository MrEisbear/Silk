from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask import Flask

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="redis://localhost:6379",
    strategy="fixed-window",
    default_limits=["200 per minute"]
)


def init_limiter(app: Flask) -> None:
    limiter.init_app(app)
