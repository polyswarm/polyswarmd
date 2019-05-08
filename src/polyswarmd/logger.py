import logging
import signal

from datetime import datetime
from pythonjsonlogger import jsonlogger


def init_logging(log_format, log_level):
    """
    Logic to support JSON logging.
    """
    logger_config = LoggerConfig(log_format, log_level)
    logger_config.configure()


class LoggerConfig:
    LEVELS = [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL]

    def __init__(self, log_format, log_level=logging.WARNING):
        self.log_format = log_format
        self.log_level = log_level

    def configure(self):
        logger = logging.getLogger()
        if self.log_format and self.log_format in ['json', 'datadog']:
            log_handler = logging.StreamHandler()
            formatter = PolyswarmdJsonFormatter('(timestamp) (level) (name) (message)')
            log_handler.setFormatter(formatter)
            logger.addHandler(log_handler)
            logger.setLevel(self.log_level)
            logger.info("Logging in JSON format.")
        elif not logger.handlers:
            # logger.handlers will have a value during pytest
            logging.basicConfig(level=self.log_level)
            logger.info("Logging in text format.")
        else:
            logger.setLevel(self.log_level)
            logger.info("Logging in text format.")

        signal.signal(signal.SIGUSR1, self.__signal_handler)

    def set_level(self, new_level):
        self.log_level = new_level
        logger = logging.getLogger()
        logger.setLevel(self.log_level)
        logger.log(self.log_level, f'Changed log level')

    def __signal_handler(self, _signum, _frame):
        try:
            cur_index = self.LEVELS.index(self.log_level)
        except ValueError:
            raise ValueError('Invalid logging level')

        index = 0 if cur_index == len(self.LEVELS) - 1 else cur_index + 1
        self.set_level(self.LEVELS[index])


class PolyswarmdJsonFormatter(jsonlogger.JsonFormatter):
    """
    Class to add custom JSON fields to our logger.
    Presently just adds a timestamp if one isn't present and the log level.
    INFO: https://github.com/madzak/python-json-logger#customizing-fields
    """

    def add_fields(self, log_record, record, message_dict):
        super(PolyswarmdJsonFormatter, self).add_fields(log_record, record, message_dict)
        if not log_record.get('timestamp'):
            # this doesn't use record.created, so it is slightly off
            now = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            log_record['timestamp'] = now
        if log_record.get('level'):
            log_record['level'] = log_record['level'].upper()
        else:
            log_record['level'] = record.levelname
