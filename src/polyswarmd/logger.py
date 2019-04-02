import logging

from datetime import datetime
from pythonjsonlogger import jsonlogger


def init_logging(log_format, log_level):
    """
    Logic to support JSON logging.
    """
    logger = logging.getLogger()
    if log_format and log_format in ['json', 'datadog']:
        logHandler = logging.StreamHandler()
        formatter = PolyswarmdJsonFormatter('(timestamp) (level) (name) (message)')
        logHandler.setFormatter(formatter)
        logger.addHandler(logHandler)
        logger.setLevel(log_level)
        logger.info("Logging in JSON format.")
    else:
        logging.basicConfig(level=log_level)
        logger.info("Logging in text format.")


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
