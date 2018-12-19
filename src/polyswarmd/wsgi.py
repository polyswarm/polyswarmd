import logging
import os

from polyswarmd.logger import init_logging
init_logging(os.environ.get('LOG_FORMAT'), logging.INFO)

from polyswarmd import app as application
