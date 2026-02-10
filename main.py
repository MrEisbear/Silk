try:
    from core.logger import logger
    from ruamel.yaml import YAML
    from core.coreC import Configure
    import dotenv
    from flask import Flask
except (ImportError, ModuleNotFoundError) as e:
    print(f"Failed to import module: {e}")
    exit(1)
# Start the App

# Load Configurator Util
try:
    config = Configure("config.yml")
except FileNotFoundError:
    logger.fatal("Config file not found; make sure config.yml exists!")
    exit(1)

# Set Logger Mode with help of the config
print(config.get("environment", "log_level"))
logger.set_mode(config.get("environment", "log_level"))

# Load dotenv with config or default (.env)
env = config.get("environment", "env_file")
if env == None:
    env = ".env"
dotenv.load_dotenv(env)
from core.database import db_helper
#Create the flask app and start the database
app = Flask(__name__)

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