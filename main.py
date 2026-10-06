from api_analytics.flask import add_middleware
from gevent import monkey
monkey.patch_all()

try:
    from core.logger import logger
except (ImportError, ModuleNotFoundError) as e:
    print(f"Failed to launch logger. Logger is required for this API. Is it installed?: {e}")
    exit(1)
try:
    from ruamel.yaml import YAML
    from core.coreC import Configure
    import dotenv
    from flask_openapi3 import Info, OpenAPI
    from werkzeug.middleware.proxy_fix import ProxyFix
except (ImportError, ModuleNotFoundError) as e:
    logger.fatal(f"Failed to import modules: {e}")
    exit(1)
# Start the App
# Load Configurator Util
try:
    config = Configure("config.yml")
except FileNotFoundError:
    logger.fatal("Config file not found; make sure config.yml exists!")
    exit(1)

# Set Logger Mode with help of the config
logger.set_mode(str(config.get_str("environment", "log_level")))

# Load dotenv with config or default (.env)
env = config.get("environment", "env_file")
if env == None:
    env = ".env"
dotenv.load_dotenv(env)
from core.database import db_helper
# Create the Flask app and OpenAPI documentation.
app = OpenAPI(
    __name__,
    info=Info(title="SilkCore API", version=str(config.get("version", default="1.0.0"))),
    security_schemes={
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Provide a session JWT or a Silk API key beginning with silk_api_.",
        }
    },
    doc_prefix="/docs",
    doc_url="/openapi.json",
)
app.add_url_rule(
    "/openapi.json",
    endpoint="openapi_spec_alias",
    view_func=lambda: app.api_doc,
)
add_middleware(app, "945c3c4f-8ddb-4356-a3cf-e7f15c2a4d8d")  # Add middleware
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
# Set CORS
from flask_cors import CORS
CORS(app,
     origins=r"https?://.*",
     methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
     supports_credentials=True,
     allow_headers=["Content-Type", "Authorization", "X-Requested-With"])

# Register blueprints and Start App
from routes import register_blueprints, initStatus
initStatus()
register_blueprints(app)
# Initialize Rate Limiter
from core.limiter import init_limiter
init_limiter(app)

app.teardown_appcontext(db_helper.close_db)

logger.info("App started!")
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=1236, debug=True, use_reloader=False)
