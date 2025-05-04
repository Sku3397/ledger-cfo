import os
from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from google.cloud.sql.connector import Connector, IPTypes
import pg8000
from contextlib import contextmanager
import logging

from .config import get_secret

logger = logging.getLogger(__name__)

# Global engine variable - initialize once
_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None
Base = declarative_base()


def get_db_connection_details() -> dict:
    """Fetches database connection details from Secret Manager."""
    logger.info("Fetching database connection details from Secret Manager.")
    try:
        db_user = get_secret("DB_USER")
        db_pass = get_secret("DB_PASS")
        db_name = get_secret("DB_NAME")
        instance_connection_name = get_secret("INSTANCE_CONNECTION_NAME") # e.g., "project:region:instance"

        if not all([db_user, db_pass, db_name, instance_connection_name]):
            raise ValueError("One or more database connection secrets are missing.")

        return {
            "user": db_user,
            "password": db_pass,
            "db": db_name,
            "instance_connection_name": instance_connection_name,
        }
    except Exception as e:
        logger.error(f"Failed to get DB connection details from Secret Manager: {e}", exc_info=True)
        raise

def init_db_engine(test_config=None) -> Engine:
    """
    Initializes the SQLAlchemy engine using Cloud SQL Python Connector.
    Uses IAM DB Auth if GOOGLE_APPLICATION_CREDENTIALS env var is set,
    otherwise uses password authentication.
    """
    global _engine, _SessionLocal
    if _engine is not None:
        logger.info("Database engine already initialized.")
        return _engine

    logger.info("Initializing database engine...")
    try:
        if test_config:
            # Use in-memory SQLite for testing
            logger.info("Using in-memory SQLite database for testing.")
            _engine = create_engine("sqlite:///:memory:")
        else:
            connector = Connector()
            conn_details = get_db_connection_details()

            # Determine auth type
            enable_iam_auth = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") is not None
            if enable_iam_auth:
                logger.info("Using IAM database authentication.")
            else:
                logger.info("Using standard password authentication.")


            def getconn() -> pg8000.dbapi.Connection:
                conn: pg8000.dbapi.Connection = connector.connect(
                    conn_details["instance_connection_name"],
                    "pg8000",
                    user=conn_details["user"],
                    password=conn_details["password"],
                    db=conn_details["db"],
                    enable_iam_auth=enable_iam_auth,
                    ip_type=IPTypes.PUBLIC, # Adjust if using PRIVATE IP
                )
                return conn

            _engine = create_engine(
                "postgresql+pg8000://",
                creator=getconn,
                pool_size=5, # Adjust as needed
                max_overflow=2,
                pool_timeout=30,
                pool_recycle=1800,
            )
            logger.info("Database engine initialized successfully with Cloud SQL Connector.")

        # Create sessionmaker
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
        return _engine

    except Exception as e:
        logger.error(f"Failed to initialize database engine: {e}", exc_info=True)
        # Perform cleanup
        if 'connector' in locals() and connector:
            connector.close()
        raise

@contextmanager
def get_db_session() -> Session:
    """Provide a transactional scope around a series of operations."""
    global _SessionLocal
    if _SessionLocal is None:
        raise RuntimeError("Database session factory not initialized. Call init_db_engine first.")

    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        logger.error("Database transaction failed. Rolled back.", exc_info=True)
        raise
    finally:
        session.close()

def get_engine() -> Engine:
    """Returns the initialized engine."""
    if _engine is None:
        raise RuntimeError("Database engine not initialized. Call init_db_engine first.")
    return _engine

# Example of initializing and creating tables (call this once at app startup)
def create_db_tables():
    logger.info("Attempting to create database tables if they don't exist...")
    try:
        engine = get_engine() # Ensure engine is initialized
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables checked/created successfully.")
    except Exception as e:
        logger.error(f"Failed to create database tables: {e}", exc_info=True)
        raise 