"""
Logging utility for Lambda functions.
"""
import json
import logging
from typing import Any, Dict


# Configure logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def log_info(message: str, **kwargs):
    """Log info level message with structured data."""
    log_data = {'level': 'INFO', 'message': message}
    log_data.update(kwargs)
    logger.info(json.dumps(log_data))


def log_error(message: str, error: Exception = None, **kwargs):
    """Log error level message with structured data."""
    log_data = {'level': 'ERROR', 'message': message}
    if error:
        log_data['error'] = str(error)
        log_data['error_type'] = type(error).__name__
    log_data.update(kwargs)
    logger.error(json.dumps(log_data))


def log_warning(message: str, **kwargs):
    """Log warning level message with structured data."""
    log_data = {'level': 'WARNING', 'message': message}
    log_data.update(kwargs)
    logger.warning(json.dumps(log_data))


def log_debug(message: str, **kwargs):
    """Log debug level message with structured data."""
    log_data = {'level': 'DEBUG', 'message': message}
    log_data.update(kwargs)
    logger.debug(json.dumps(log_data))



