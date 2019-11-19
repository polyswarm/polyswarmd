import gevent

try:
    import ujson as json
except ImportError:
    import json

from gevent.lock import BoundedSemaphore
from polyswarmd.utils import logging
from polyswarmd.websockets.filter import FilterManager
from signal import SIGQUIT

logger = logging.getLogger(__name__)


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
        logger.debug('Sending: %s', message)
        msg = json.dumps(message)
        with self.websockets_lock:
            for ws in self.websockets:
                logger.debug('Sending WebSocket %s %s', ws, message)
                ws.send(msg)

    def flush_filters(self):
        """
        Clear filters of existing entires
        """
        self.block_filter.get_new_entries()
        self.fee_filter.get_new_entries()
        self.window_filter.get_new_entries()
        self.bounty_filter.get_new_entries()
        self.assertion_filter.get_new_entries()
        self.vote_filter.get_new_entries()
        self.quorum_filiter.get_new_entries()
        self.settled_filter.get_new_entries()
        self.reveal_filter.get_new_entries()
        self.deprecated_filter.get_new_entries()
        if self.init_filter:
            self.init_filter.get_new_entries()

    # noinspection PyBroadException
    def poll(self):
        """
        Continually poll all Ethereum filters as long as there are WebSockets listening
        """
        # Start the pool
        try:
            with self.filter_manager.fetch() as results:
                for messages in results:
                    if self.websockets == None:
                        return
                    for msg in messages:
                        self.broadcast(msg)

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
                if len(self.websockets) == 0:
                    self.websockets = None
                    self.filter_manager.flush()
