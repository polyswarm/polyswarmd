from signal import SIGQUIT
from typing import AnyStr, List, Optional, SupportsBytes, Union

import gevent
from gevent.lock import BoundedSemaphore

from polyswarmd.event_message import WebSocket
from polyswarmd.utils import logging
from polyswarmd.websockets.filter import FilterManager

logger = logging.getLogger(__name__)


class WebsocketConnectionAbortedError(Exception):
    """Exception thrown when no clients exist to broadcast to"""
    pass


class EthereumRpc:
    """
    This class periodically polls several geth filters, and multicasts the results across any open WebSockets
    """
    filter_manager = FilterManager()
    websockets: Optional[List[WebSocket]] = None
    websockets_lock: BoundedSemaphore = BoundedSemaphore(1)

    def __init__(self, chain):
        self.chain = chain

    def broadcast(self, message: Union[AnyStr, SupportsBytes]):
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
            self.websockets = None
        except gevent.GreenletExit:
            logger.exception('Greenlet killed, not restarting')
        except Exception:
            logger.exception('Exception in filter checks, restarting greenlet')
            # Creates a new greenlet with all new filters and let's this one die.
            gevent.spawn(self.poll)

    def register(self, ws: WebSocket):
        """
        Register a WebSocket with the rpc nodes
        Gets all events going forward
        :param ws: WebSocket wrapper to register
        """
        with self.websockets_lock:
            logger.debug('Registering WebSocket %s', id(ws))
            if self.websockets is None:
                self.websockets = [ws]
                logger.debug('First WebSocket registered, starting greenlet')
                self.filter_manager.setup_event_filters(self.chain)
                greenlet = gevent.spawn(self.poll)
                gevent.signal(SIGQUIT, greenlet.kill)
            else:
                self.websockets.append(ws)

    def unregister(self, ws: WebSocket):
        """
        Remove a Websocket wrapper object
        :param ws: WebSocket to remove
        """
        logger.debug('Unregistering WebSocket %s', id(ws))
        with self.websockets_lock:
            if ws in self.websockets:
                logger.debug('Removing WebSocket %s', id(ws))
                self.websockets.remove(ws)
