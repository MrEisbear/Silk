# coreDB.py
from contextlib import contextmanager
from typing import Any, Generator
import os
import pymysql.cursors
from flask import g, has_app_context
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from core.logger import logger


class PooledConnectionWrapper:
    """
    Wraps SQLAlchemy's raw pooled connection to maintain 100% backward compatibility
    with mysql.connector dictionary cursors and transaction APIs.
    """
    def __init__(self, raw_conn: Any):
        self._conn = raw_conn

    def cursor(self, *args: Any, **kwargs: Any) -> Any:
        # Default to DictCursor or when dictionary=True is explicitly passed
        if kwargs.get("dictionary") is True or (not args and not kwargs):
            kwargs.pop("dictionary", None)
            return self._conn.cursor(pymysql.cursors.DictCursor)
        kwargs.pop("dictionary", None)
        return self._conn.cursor(*args, **kwargs)

    def start_transaction(self) -> None:
        self._conn.begin()

    def begin(self) -> None:
        self._conn.begin()

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()

    @property
    def autocommit(self) -> bool:
        return bool(self._conn.get_autocommit())

    @autocommit.setter
    def autocommit(self, val: bool) -> None:
        self._conn.autocommit(val)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)


class DataBase:
    def __init__(self) -> None:
        logger.verbose("Initializing database connection pool...")
        self.host = os.getenv("DB_HOST")
        self.user = os.getenv("DB_USER")
        self.port = os.getenv("DB_PORT")
        self.password = os.getenv("DB_PASSWORD")
        self.database = os.getenv("DB_NAME")

        if not all([self.user, self.password, self.database]):
            logger.fatal("Missing database environment variables!")
            raise RuntimeError("Missing database environment variables!")

        if not self.port:
            self.port = 3306
            logger.warning("DB_PORT not set, using default port (3306)")
        self.port = int(self.port)

        url = f"mysql+pymysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}?charset=utf8mb4"
        self.engine = create_engine(
            url,
            pool_size=15,
            max_overflow=25,
            pool_recycle=1800,
            pool_pre_ping=True,
        )
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

        # Pre-warm connection pool at startup to eliminate initial request delay
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.verbose("Database connection pool initialized and pre-warmed successfully!")
        except Exception as e:
            logger.error(f"Database pool pre-warm error: {e}")

    # ==========================================
    # Modern ORM API (For new routes)
    # ==========================================

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        """
        Context manager for SQLAlchemy ORM sessions.
        Automatically commits on successful exit, rolls back on error, and closes cleanly.
        """
        sess: Session = self.session_factory()
        try:
            yield sess
            sess.commit()
        except Exception:
            sess.rollback()
            raise
        finally:
            sess.close()

    def get_session(self) -> Session:
        """Get or create an ORM session for the current Flask request context."""
        if has_app_context():
            if "db_session" not in g:
                g.db_session = self.session_factory()
            return g.db_session
        return self.session_factory()

    # ==========================================
    # Legacy Raw SQL API (100% Backward Compatible)
    # ==========================================

    def get_db(self) -> PooledConnectionWrapper:
        """Get or checkout a pooled DB connection for the current request context."""
        if has_app_context():
            if "db" not in g:
                logger.verbose("Checking out database connection from pool...")
                raw = self.engine.raw_connection()
                g.db = PooledConnectionWrapper(raw)
                logger.verbose("Database connection checked out from pool!")
            return g.db
        # Outside Flask application context (scripts, background tasks)
        raw = self.engine.raw_connection()
        return PooledConnectionWrapper(raw)

    def get_cursor(self) -> Any:
        """Get a dictionary cursor for the current request."""
        return self.get_db().cursor(dictionary=True)

    def close_db(self, e: Any = None) -> None:
        """Close DB connections and ORM sessions for the current request."""
        if has_app_context():
            # Close legacy connection wrapper (returns connection to pool)
            db = g.pop("db", None)
            if db is not None:
                try:
                    db.close()
                except Exception as ex:
                    logger.warning(f"Error returning connection to pool: {ex}")

            # Close ORM session
            sess: Session | None = g.pop("db_session", None)
            if sess is not None:
                try:
                    sess.close()
                except Exception as ex:
                    logger.warning(f"Error closing request session: {ex}")

    @contextmanager
    def cursor(self) -> Generator[Any, None, None]:
        """Context manager yielding a dictionary cursor."""
        in_flask = has_app_context()
        conn = self.get_db()
        cur = conn.cursor(dictionary=True)
        try:
            yield cur
        finally:
            cur.close()
            if not in_flask:
                conn.close()

    @contextmanager
    def transaction(self) -> Generator[Any, None, None]:
        """Context manager for atomic transactions."""
        in_flask = has_app_context()
        db = self.get_db()
        db.autocommit = False
        try:
            db.start_transaction()
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.autocommit = True
            if not in_flask:
                db.close()