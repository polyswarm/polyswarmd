import logging
import sys
import os

from polyswarmd.logger import init_logging


def app(*args, **kwargs):
    # Can't directly pass command line arguments via gunicorn, but can pass arguments to callable
    # https://stackoverflow.com/questions/8495367/using-additional-command-line-arguments-with-gunicorn
    log_format = os.environ.get('LOG_FORMAT', kwargs.get('log_format', 'text'))

    log_level = os.environ.get('LOG_LEVEL', kwargs.get('log_level', 'WARNING'))
    log_level = getattr(logging, log_level.upper(), None)
    if not isinstance(log_level, int):
        logging.error('Invalid log level')
        sys.exit(-1)

    init_logging(log_format, log_level)

    from polyswarmd import app as application
    return application
