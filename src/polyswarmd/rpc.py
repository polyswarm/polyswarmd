import time
from typing import Optional

import web3.eth
from web3.utils import Filter
from requests.exceptions import ConnectionError

import gevent
from gevent.lock import BoundedSemaphore
from gevent.pool import Pool
from polyswarmd.utils import logging
from polyswarmd.websockets.messages import (WebsocketEventlogMessage, Deprecated, FeesUpdated, InitializedChannel,
                                            LatestEvent, NewAssertion, NewBounty, NewVote, QuorumReached,
                                            RevealedAssertion, SettledBounty, WindowsUpdated)

logger = logging.getLogger(__name__)


class FilterManager(object):
    """Manages access to filtered Ethereum events."""

    # Maximum amount of time to back-off on event fetching.
    MAXIMUM_WAIT = 20

    def __init__(self):
        self.filters = []
        self.formatters = {}
        self.pool = None

    def register(self, flt: Filter, ws_serializer: Optional[WebsocketEventlogMessage]):
        "Add a new filter, with an optional associated WebsocketMessage-serializer class"
        self.filters.append(flt)
        self.formatters[flt] = ws_serializer

    def __del__(self):
        "Destructor to be run when a filter manager is no longer needed"
        if self.pool:
            self.pool.kill()
        for filt in self.filters:
            web3.eth.uninstallFilter(filt.filter_id)
        self.formatters = {}
        self.filters = []

    def flush(self):
        for filt in self.filters:
            filt.get_new_entries()

    def event_pool(self, callback, group=None):
        """Maintains a gevent Pool of filter event entry fetchers.

        The pool is filled by `fetch_filter', which automatically creates
        another greenlet of itself. It may also alter how long it waits before
        that greenlet is run based on if:

            - No entries were returned by this filter (it doesn't need to be checked as frequently)
            - A connection error occurred (maybe geth is down, try to back off and wait)
        """
        if group:
            self.group = group
        else:
            self.group = Pool(len(self.filters))

        def fetch_filter(filt, wait=1):
            if filt not in self.formatters:
                raise ValueError("Filter does not have associated formatter")

            # Run the `callback' on every new filter entry
            try:
                entries = filt.get_new_entries()
                format_cls = self.formatters[filt]
                for entry in entries:
                    callback(format_cls(entry))
                # If we aren't receiving much traffic on this channel, back off.
                if len(entries) == 0 and wait < self.MAXIMUM_WAIT:
                    wait = wait + 1
                elif wait > self.MAXIMUM_WAIT // 2:
                    wait = wait - self.MAXIMUM_WAIT // 4
                elif wait >= 1:
                    wait = wait - 1
            except ConnectionError:
                if wait < self.MAXIMUM_WAIT:
                    wait += 5
                logger.exception('ConnectionError occcurred, backing off...')

            # Spawn the next version of this instance
            self.group.start(gevent.spawn_later(wait, fetch_filter, filt, wait))

        for filt in self.filters:
            self.group.add(gevent.spawn(fetch_filter, filt))

        return self.group


class EthereumRpc:
    """
    This class periodically polls several geth filters, and multicasts the results across any open WebSockets
    """
    def __init__(self, chain):
        self.chain = chain
        self.block_filter = None
        self.websockets_lock = BoundedSemaphore(1)
        self.websockets = None

    @staticmethod
    def compute_sleep(diff):
        """ Adjusts sleep based on the difference of last iteration.
        If last iteration took over 500 millis, adjust this sleep lower. Otherwise, return 500


        :param diff: time in millis
        :return: sleep time in millis
        """
        if diff > 500:
            sleep = 1000 - diff
            return sleep if sleep > 0 else 0
        else:
            return 500

    def broadcast(self, message):
        """
        Send a message to all connected WebSockets
        :param message: dict to be converted to json and sent
        """
        with self.websockets_lock:
            for ws in self.websockets:
                ws.send(message)

    # noinspection PyBroadException
    async def poll(self):
        """
        Continually poll all Ethereum filters as long as there are WebSockets listening
        """
        # Setup filters
        self.fmanager = FilterManager()
        for cls in [
                FeesUpdated, WindowsUpdated, NewBounty, NewAssertion, NewVote, QuorumReached, SettledBounty,
                RevealedAssertion, Deprecated
        ]:
            self.fmanager.register(cls, self.chain.bounty_registry.contract.eventFilter(cls.event_name))

        self.fmanager.register(LatestEvent, self.chain.w3.eth.filter('latest'))

        if self.chain.offer_registry.contract:
            self.fmanager.register(InitializedChannel,
                                   self.chain.offer_registry.contract.eventFilter('InitializedChannel'))

        # Start the pool
        try:
            self.fmanager.event_pool(self.broadcast).join()
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
            elif not self.websockets:
                # Clear the filters of old data.
                # Possible when last WebSocket closes & a new one opens before the 1 poll sleep ends
                logger.debug('Clearing out of date filter events.')
                self.fmanager.flush()

            self.websockets.append(ws)

        if start:
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
                self.websockets.remove(ws)
