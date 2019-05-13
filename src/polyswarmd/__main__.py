import click
import logging
import sys

from gevent import pywsgi
from geventwebsocket.handler import WebSocketHandler

from polyswarmd.logger import init_logging

logger = logging.getLogger(__name__)


@click.command()
@click.option('--log-format', envvar='LOG_FORMAT', default='text', help='Logging format')
@click.option('--log-level', envvar='LOG_LEVEL', default='WARNING', help='Logging level')
@click.option('--host', default='', help='Host to listen on')
@click.option('--port', default=31337, help='Port to listen on')
def main(log_format, log_level, host, port):
    log_level = getattr(logging, log_level.upper(), None)
    if not isinstance(log_level, int):
        logging.error('Invalid log level')
        sys.exit(-1)

    init_logging(log_format, log_level)

    from polyswarmd import app
    server = pywsgi.WSGIServer((host, port), app, handler_class=WebSocketHandler)

    logger.critical("polyswarmd is ready!")
    server.serve_forever()


if __name__ == '__main__':
    main()
