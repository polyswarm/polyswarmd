import gevent
from gevent.lock import BoundedSemaphore
from polyswarmd.utils import logging
from polyswarmd.websockets.filter import (FilterManager)

logger = logging.getLogger(__name__)

class EthereumRpc:
    """
    This class periodically polls several geth filters, and multicasts the results across any open WebSockets
    """
    def __init__(self, chain):
        self.chain = chain
        self.block_filter = None
        self.websockets_lock = BoundedSemaphore(1)
        self.websockets = None

    def broadcast(self, message):
        """
        Send a message to all connected WebSockets
        :param message: dict to be converted to json and sent
        """
        with self.websockets_lock:
            for ws in self.websockets:
                ws.send(message)

    # noinspection PyBroadException
    def poll(self):
        """
        Continually poll all Ethereum filters as long as there are WebSockets listening
        """
        # Start the pool
        try:
            self.filter_manager.event_pool(self.broadcast).join()
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
        start = False
        # Cross greenlet list
        with self.websockets_lock:
            if self.websockets is None:
                start = True
                self.websockets = []

            self.websockets.append(ws)

        if start:
            # Setup filters
            self.filter_manager = FilterManager()
            self.filter_manager.setup_event_filters(self.chain)
            logger.debug('First WebSocket registered, starting greenlet')
            gevent.spawn(self.poll)

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
