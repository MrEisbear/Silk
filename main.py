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
    from flask import Flask
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
#Create the flask app and start the database
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
# Set CORS
from flask_cors import CORS
CORS(app, origins=["https://brickrigs.de"], supports_credentials=True)

# Register blueprints and Start App
from routes import register_blueprints, initStatus
initStatus()
register_blueprints(app)
logger.info("App started!")
if __name__ == "__main__":
    app.teardown_appcontext(db_helper.close_db)
    app.run(host="0.0.0.0", port=1236, debug=True, use_reloader=False)