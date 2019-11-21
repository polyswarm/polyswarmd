import logging
import sys
import os

from polyswarmd.logger import init_logging

logger = logging.getLogger(__name__)


def app(*args, **kwargs):
    # Can't directly pass command line arguments via gunicorn, but can pass arguments to callable
    # https://stackoverflow.com/questions/8495367/using-additional-command-line-arguments-with-gunicorn
    log_format = os.environ.get('LOG_FORMAT', kwargs.get('log_format', 'text'))

    log_level = os.environ.get('LOG_LEVEL', kwargs.get('log_level', 'WARNING'))
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

    from polyswarmd import app as application

    logger.critical("polyswarmd is ready!")
    return application
