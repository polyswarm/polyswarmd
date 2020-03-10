import logging
import os
import sys

from polyswarmd.utils.logger import init_logging

logger = logging.getLogger(__name__)

# Can't directly pass command line arguments via gunicorn, but can pass arguments to callable
# https://stackoverflow.com/questions/8495367/using-additional-command-line-arguments-with-gunicorn
log_format = os.environ.get('LOG_FORMAT', 'TEXT')

log_level = os.environ.get('LOG_LEVEL', 'WARNING')
log_level = getattr(logging, log_level.upper(), None)

try:
    init_logging(log_format, log_level)
except (TypeError, ValueError) as e:
    logging.error('Invalid log level')
    logging.exception(e)
    sys.exit(10)
except Exception as e:
    logging.exception(e)
    sys.exit(-1)

logger.critical("polyswarmd is ready!")

from polyswarmd.app import app
from polyswarmd.urls import *
