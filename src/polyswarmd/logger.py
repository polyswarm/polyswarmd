import logging

from datetime import datetime
from pythonjsonlogger import jsonlogger


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