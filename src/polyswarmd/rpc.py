from signal import SIGQUIT

import gevent
from gevent.lock import BoundedSemaphore

from polyswarmd.utils import logging
from polyswarmd.websockets.filter import FilterManager

logger = logging.getLogger(__name__)


class WebsocketConnectionAbortedError(Exception):
    """Exception thrown when broadcast cannot send to can clients"""
    pass


class EthereumRpc:
    """
    This class periodically polls several geth filters, and multicasts the results across any open WebSockets
    """
    filter_manager = FilterManager()

    def __init__(self, chain):
        self.chain = chain
        self.websockets_lock = BoundedSemaphore(1)
        self.websockets = None

    def broadcast(self, message):
        """
        Send a message to all connected WebSockets
        :param message: dict to be converted to json and sent
        """
        # XXX This can be replaced with a broadcast inside the WebsocketHandlerApplication
        with self.websockets_lock:
            if len(self.websockets) == 0:
                raise WebsocketConnectionAbortedError
            for ws in self.websockets:
                ws.send(message)

    # noinspection PyBroadException
    def poll(self):
        """
        Continually poll all Ethereum filters as long as there are WebSockets listening
        """
        # Start the pool
        try:
            with self.filter_manager.fetch() as results:
                for messages in results:
                    for msg in messages:
                        self.broadcast(msg)
        except WebsocketConnectionAbortedError:
            logger.exception("Shutting down poll()")
            self.filter_manager.flush()
            self.websockets = None
        except Exception:
            logger.exception('Exception in filter checks, restarting greenlet')
            # Creates a new greenlet with all new filters and let's this one die.
            gevent.spawn(self.poll)

    def register(self, ws):
        """
        Register a WebSocket with the rpc nodes
        Gets all events going forward
        :param ws: WebSocket wrapper to register
        """
        with self.websockets_lock:
            if self.websockets is None:
                self.websockets = [ws]
                logger.debug('First WebSocket registered, starting greenlet')
                self.filter_manager.setup_event_filters(self.chain)
                greenlet = gevent.spawn(self.poll)
                gevent.signal(SIGQUIT, greenlet.kill)
            else:
                self.websockets.append(ws)

    def unregister(self, ws):
        """
        Remove a Websocket wrapper object
        :param ws: WebSocket to remove
        """
        logger.debug('Unregistering WebSocket %s', ws)
        with self.websockets_lock:
            if ws in self.websockets:
                logger.debug('Removing WebSocket %s', ws)
                self.websockets.remove(ws)
