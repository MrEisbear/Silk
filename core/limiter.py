from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Initialize Limiter with Redis storage
# storage_uri="redis://localhost:6379" ensures we use the local Redis server
# key_func=get_remote_address ensures we limit by IP address
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="redis://localhost:6379",
    strategy="fixed-window",
    default_limits=["200 per minute"]
)

def init_limiter(app):
    limiter.init_app(app)
