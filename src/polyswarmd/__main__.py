import click
import logging
import sys

from gevent import pywsgi
from geventwebsocket.handler import WebSocketHandler

from polyswarmd import app


@click.command()
@click.option('--log', default='INFO',
        help="Logging level")
@click.option('--host', default='',
        help='Host to listen on')
@click.option('--port', default=31337,
        help='Port to listen on')
def main(log, host, port):
    loglevel = getattr(logging, log.upper(), None)
    if not isinstance(loglevel, int):
        logging.error('invalid log level')
        sys.exit(-1)
    logging.basicConfig(level=loglevel)

    server = pywsgi.WSGIServer(
        (host, port), app, handler_class=WebSocketHandler)
    server.serve_forever()


if __name__ == '__main__':
    main()
