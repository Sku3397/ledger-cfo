import os
from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from google.cloud.sql.connector import Connector, IPTypes
import pg8000
from contextlib import contextmanager
import logging
import threading # Import threading for locking

from .config import get_secret, get_env_variable

logger = logging.getLogger(__name__)

# Global engine variable and SessionLocal - initialized lazily
_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None
_engine_lock = threading.Lock() # Lock to prevent race conditions during init

Base = declarative_base()


def get_db_connection_details() -> dict:
    """Fetches database connection details from Secret Manager."""
    logger.info("Fetching database connection details from Secret Manager.")
    try:
        db_user = get_secret("ledger-cfo-db-user")
        db_pass = get_secret("ledger-cfo-db-password")
        db_name = get_secret("ledger-cfo-db-name")
        instance_connection_name = get_secret("ledger-cfo-db-instance-conn") # e.g., "project:region:instance"
        db_port = get_env_variable("DB_PORT", "5432") # Standard PostgreSQL port

        if not all([db_user, db_pass, db_name, instance_connection_name]):
            raise ValueError("One or more database connection secrets are missing.")

        return {
            "user": db_user,
            "password": db_pass,
            "db": db_name,
            "instance_connection_name": instance_connection_name,
            "port": db_port,
        }
    except Exception as e:
        logger.error(f"Failed to get DB connection details from Secret Manager: {e}", exc_info=True)
        raise

# This function is now internal, called only when needed by get_db_session or get_engine
def _initialize_database(test_config=None):
    """
    Internal function to initialize the SQLAlchemy engine and session factory.
    Uses Cloud SQL Python Connector or SQLite for tests.
    Creates tables after successful engine initialization.
    """
    global _engine, _SessionLocal
    logger.info("Attempting to initialize database engine and session factory...")
    try:
        if test_config:
            # Use in-memory SQLite for testing
            logger.info("Using in-memory SQLite database for testing.")
            temp_engine = create_engine("sqlite:///:memory:")
        else:
            connector = Connector()
            conn_details = get_db_connection_details()

            # Strip whitespace/control characters from credentials
            db_user = conn_details.get("user", "").strip()
            db_pass = conn_details.get("password", "").strip()
            db_name = conn_details.get("db", "").strip()
            instance_connection_name = conn_details.get("instance_connection_name", "").strip()

            if not all([db_user, db_pass, db_name, instance_connection_name]):
                 # Re-check after stripping
                 raise ValueError("One or more database connection details are missing or empty after stripping.")

            # Determine auth type
            enable_iam_auth = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") is not None
            if enable_iam_auth:
                logger.info("Using IAM database authentication.")
            else:
                logger.info("Using standard password authentication.")


            def getconn() -> pg8000.dbapi.Connection:
                conn: pg8000.dbapi.Connection = connector.connect(
                    instance_connection_name, # Use stripped variable
                    "pg8000",
                    user=db_user,            # Use stripped variable
                    password=db_pass,        # Use stripped variable
                    db=db_name,              # Use stripped variable
                    enable_iam_auth=enable_iam_auth,
                    ip_type=IPTypes.PUBLIC, # Adjust if using PRIVATE IP
                )
                return conn

            temp_engine = create_engine(
                "postgresql+pg8000://",
                creator=getconn,
                pool_size=5, # Adjust as needed
                max_overflow=2,
                pool_timeout=30,
                pool_recycle=1800,
            )
            logger.info("Database engine created successfully with Cloud SQL Connector.")

        # -- Create tables ---
        logger.info("Attempting to create database tables if they don't exist...")
        try:
            # Make sure all models using Base are imported before this point
            # Ensure models are loaded, e.g., by importing them in the module
            # calling get_db_session/get_engine for the first time (__main__.py)
            from .. import models # Adjust if models are elsewhere relative to database.py
            Base.metadata.create_all(bind=temp_engine)
            logger.info("Database tables checked/created successfully.")
        except Exception as table_exc:
            logger.error(f"Failed to create database tables: {table_exc}", exc_info=True)
            # Decide if failure to create tables should prevent engine use
            # For now, we continue but log the error. Depending on app logic,
            # you might want to raise the exception here.
            # raise # Optionally re-raise

        # --- Assign to globals ---
        _engine = temp_engine
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
        logger.info("Database engine and session factory initialized globally.")

    except Exception as e:
        logger.error(f"Failed to initialize database engine: {e}", exc_info=True)
        # Perform cleanup if connector was created
        if 'connector' in locals() and connector:
            try:
                connector.close()
            except Exception as close_err:
                 logger.error(f"Error closing Cloud SQL connector: {close_err}", exc_info=True)
        raise # Re-raise the main initialization error


@contextmanager
def get_db_session(test_config=None) -> Session:
    """
    Provide a transactional scope around a series of operations.
    Initializes the database engine and session factory on first call if needed.
    """
    global _engine, _SessionLocal, _engine_lock
    # Double-checked locking to ensure thread-safe initialization
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _initialize_database(test_config=test_config) # Pass test_config if provided

    if _SessionLocal is None:
         # This state should ideally not be reached if _initialize_database succeeded
         raise RuntimeError("Database session factory failed to initialize.")

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

def get_engine(test_config=None) -> Engine:
    """
    Returns the initialized engine, initializing it first if needed.
    """
    global _engine, _engine_lock
    # Double-checked locking
    if _engine is None:
         with _engine_lock:
             if _engine is None:
                 _initialize_database(test_config=test_config) # Pass test_config if provided

    if _engine is None:
         # This state should ideally not be reached if _initialize_database succeeded
        raise RuntimeError("Database engine failed to initialize.")
    return _engine

# Remove the standalone create_db_tables function as it's now part of _initialize_database
# # Example of initializing and creating tables (call this once at app startup)
# def create_db_tables():
#     logger.info("Attempting to create database tables if they don't exist...")
#     try:
#         engine = get_engine() # Ensure engine is initialized
#         Base.metadata.create_all(bind=engine)
#         logger.info("Database tables checked/created successfully.")
#     except Exception as e:
#         logger.error(f"Failed to create database tables: {e}", exc_info=True)
#         raise 