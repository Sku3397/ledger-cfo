import logging
import sys
from pythonjsonlogger import jsonlogger

def configure_logging():
    """Configures logging to output JSON format."""
    logger = logging.getLogger()
    # Remove existing handlers if any
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Create a handler that outputs to stdout
    handler = logging.StreamHandler(sys.stdout)

    # Use JsonFormatter
    # Include standard LogRecord attributes, plus specific ones for Cloud Logging
    # https://cloud.google.com/logging/docs/structured-logging#special-payload-fields
    # Add custom fields as needed
    formatter = jsonlogger.JsonFormatter(
        '%(sctime)s %(levelname)s %(name)s %(message)s ' 
        '%(pathname)s %(lineno)d %(funcName)s '
        '%(email_id)s %(intent)s %(task_id)s', # Example custom fields (need context)
        rename_fields={'asctime': 'timestamp', 'levelname': 'severity'},
        datefmt='%Y-%m-%dT%H:%M:%S.%fZ' # ISO 8601 format preferred by Cloud Logging
    )

    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    # Configure Flask and Werkzeug logging similarly if possible
    # This might involve accessing their loggers directly after app creation
    # Example: logging.getLogger('werkzeug').addHandler(handler)
    # Note: Gunicorn logging might need separate configuration via its config file/args

    logger.info("JSON logging configured.")


def add_context_to_log_record(record, context_dict):
    """Helper to add context to a log record before emitting."""
    for key, value in context_dict.items():
        setattr(record, key, value)
    return record 