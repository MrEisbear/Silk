import mysql.connector
from flask import g
import dotenv
import os
from main import logger
from main import config

# Core Database Module

class DataBase:
    def __init__(self):
        env = config.get("environment", "en_file")
        if env == None:
            env = ".env"
        dotenv.load_dotenv()
        self.host = os.getenv("HOST")
        self.user = os.getenv("USER")
        self.password = os.getenv("PASSWORD")
        self.database = os.getenv("DATABASE")
        self.autocommit = True
        logger.verbose("Loading new Database...")

    def get_db(self):
        if "db" not in g:
            g.db = mysql.connector.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database,
                autocommit=self.autocommit
            )
        logger.verbose("New Database connection opened!")
        return g.db
        

    def close_db(self, e=None):
        logger.verbose("A Database connection is being closed!")
        db = g.pop("db", None)
        if db is not None:
            db.close()