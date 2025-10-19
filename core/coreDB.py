# db.py
from contextlib import contextmanager
import mysql.connector
from flask import g
import os
from core.logger import logger

class DataBase:
    def __init__(self):
        logger.verbose("Initializing database connection...")
        self.host = os.getenv("DB_HOST")
        self.user = os.getenv("DB_USER")
        self.password = os.getenv("DB_PASSWORD")
        self.database = os.getenv("DB_NAME")
        if not all([self.user, self.password, self.database]):
            logger.fatal("Missing database environment variables!")
            raise RuntimeError("Missing database environment variables!")

    def get_db(self):
        """Get or create a DB connection for the current request."""
        if "db" not in g:
            logger.verbose("Opening new database connection...")
            g.db = mysql.connector.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database,
                autocommit=True,
            )
        logger.verbose("New Database connection opened!")
        return g.db

    def get_cursor(self):
        """Get a dictionary cursor for the current request."""
        return self.get_db().cursor(dictionary=True)

    def close_db(self, e=None):
        """Close the DB connection for the current request."""
        db = g.pop("db", None)
        if db is not None:
            logger.verbose("Closing database connection...")
            db.close()
            
    @contextmanager
    def cursor(self):
        cur = self.get_cursor()
        try:
            yield cur
        finally:
            cur.close()