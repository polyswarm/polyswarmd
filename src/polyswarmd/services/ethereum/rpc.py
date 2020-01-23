from typing import Any, Iterator, List, Optional

from gevent.lock import BoundedSemaphore

from polyswarmd.utils import logging
from polyswarmd.views.event_message import WebSocket
from polyswarmd.websockets import messages
from polyswarmd.websockets.filter import FilterManager, FormatClass, MessageT

logger = logging.getLogger(__name__)


class EthereumRpc:
    """
    This class periodically polls several geth filters, and multicasts the results across any open WebSockets
    """
    filter_manager: Optional[FilterManager]
    websockets: Optional[List[WebSocket]]
    websockets_lock: BoundedSemaphore
    chain: Any

    def __init__(self, chain):
        self.chain = chain
        self.filter_manager = None
        self.websockets = None
        self.websockets_lock = BoundedSemaphore(1)

    def __repr__(self):
        return f"<EthereumRPC Chain={self.chain}>"

    def broadcast(self, messages: Iterator[MessageT]):
        """
        Send a message to all connected WebSockets
        :param message: dict to be converted to json and sent
        """
        with self.websockets_lock:
            for ws in self.websockets:
                try:
                    for msg in messages:
                        ws.send(msg)
                except Exception:
                    logger.exception('Error adding message to the queue')
                    continue

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
                logger.debug('First WebSocket registered')
                self.setup_filter_manager()
            else:
                self.websockets.append(ws)

    def setup_filter_manager(self):
        if self.filter_manager is not None:
            logger.info("this FilterManager has already been initialized")
            return

        manager = FilterManager()

        # Setup Latest (although this could pass `w3.eth.filter` directly)
        manager.register(
            self.chain.w3.eth.filter, messages.LatestEvent.make(self.chain.w3.eth), backoff=False
        )

        # messages.NewBounty shouldn't wait or back-off from new bounties.
        bounty_contract = self.chain.bounty_registry.contract
        manager.register(bounty_contract.eventFilter, messages.NewBounty, backoff=False)

        filter_events: List[FormatClass] = [
            messages.FeesUpdated,
            messages.WindowsUpdated,
            messages.NewAssertion,
            messages.NewVote,
            messages.QuorumReached,
            messages.SettledBounty,
            messages.RevealedAssertion,
            messages.Deprecated,
            messages.Undeprecated,
        ]

        for cls in filter_events:
            manager.register(bounty_contract.eventFilter, cls)

        offer_registry = self.chain.offer_registry
        if offer_registry and offer_registry.contract:
            manager.register(offer_registry.contract.eventFilter, messages.InitializedChannel)

        # Calls `self.broadcast` with the results of each filter manager
        manager.pipe_events(self.broadcast)
        self.filter_manager = manager

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
