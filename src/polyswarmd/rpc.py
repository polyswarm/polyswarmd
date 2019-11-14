import weakref
from collections import namedtuple
from typing import Any, Callable, Collection, Container, Type

from requests.exceptions import ConnectionError

import gevent
import web3.eth
from gevent.lock import BoundedSemaphore
from gevent.pool import Pool
from polyswarmd.utils import logging
from polyswarmd.websockets.messages import (Deprecated, FeesUpdated,
                                            InitializedChannel, LatestEvent,
                                            NewAssertion, NewBounty, NewVote,
                                            QuorumReached, RevealedAssertion,
                                            SettledBounty,
                                            WebsocketFilterMessage,
                                            WindowsUpdated)
from web3.utils import Filter

logger = logging.getLogger(__name__)

# The type of a formatter used in `FilterWrapper`
FilterFormatter = Type[WebsocketFilterMessage]

class FilterWrapper(namedtuple('Filter', ['filter', 'formatter', 'wait'])):
    def __del__(self):
        web3.eth.uninstallFilter(self.filter.filter_id)
        super().__del__(self)

    def get_new_entries(self):
        for entry in self.filter.get_new_entries():
            yield self.formatter(entry)

    def __hash__(self):
        return hash(self.filter.filter_id)


class FilterManager(object):
    """Manages access to filtered Ethereum events."""

    wrappers: Collection[FilterWrapper]
    pool: Pool
    MAX_WEIGHT: int = 10

    def __init__(self):
        self.wrappers = {}
        self.pool = Pool(None)

    def register(self, flt: Filter, fmt_cls: FilterFormatter = lambda x: x, wait=1):
        "Add a new filter, with an optional associated WebsocketMessage-serializer class"
        wrapper = FilterWrapper(flt, fmt_cls, wait)
        self.wrappers.add(wrapper)
        logger.debug('Registered new filter: %s', wrapper)
        self.pool.size = (len(self.wrappers) * 2) + 1

    @property
    def filters(self):
        for filt in self.wrappers:
            yield filt

    def __del__(self):
        "Destructor to be run when a filter manager is no longer needed"
        self.pool.kill()
        self.pool = Pool(None)
        self.wrappers = {}

    def flush(self):
        logger.debug('Clearing out of date filter events.')
        for filt in self.filters:
            filt.get_new_entries()

    def event_pool(self, callback: Callable[..., Any], immediate: Container[Filter] = {NewBounty}):
        """Maintains a gevent Pool of filter event entry fetchers.

        The pool is filled by `fetch_filter', which automatically creates
        another greenlet of itself. It may also alter how long it waits before
        that greenlet is run based on if:

            - No entries were returned by this filter (it doesn't need to be checked as frequently)
            - A connection error occurred (maybe geth is down, try to back off and wait)
        """
        def fetch_filter(wrapper: FilterWrapper, wait: int = None):
            # Run the `callback' on every new filter entry
            try:
                empty_filter = True
                for entry in wrapper.get_new_entries():
                    empty_filter = False
                    callback(entry)
                if wait:
                    if empty_filter:
                        wait *= 2  # if there's no traffic, back off
                    elif wait > self.MAX_WAIT // 2:
                        wait //= 2  # but drop quickly if our wait is high w/ new traffic
                    elif wait >= 0:
                        wait -= 1  # otherwise steadily decrease
            except ConnectionError:
                if wait:
                    wait = (wait + 1) * 2
                logger.exception('ConnectionError occurred, backing off...')

            # Spawn the next version of this instance
            if wait:
                wait = min(self.MAX_WAIT, max(0.01, wait))
                self.pool.start(gevent.spawn_later(wait, fetch_filter, wrapper, wait))
            else:
                self.pool.start(gevent.spawn(fetch_filter, wrapper))

        # Greenlet's can continue to exist beyond the lifespan of the object itself, this will prevent filters from
        # cleaning up after themselves.
        for wrapper in [weakref.proxy(w) for w in self.wrappers]:
            self.pool.add(gevent.spawn(fetch_filter, wrapper, wrapper.wait))

        return self.pool


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

            bounty_contract = self.chain.bounty_registry.contract
            self.filter_manager.register(NewBounty, bounty_contract.eventFilter(NewBounty.filter_event), wait=None)

            filter_events = [
                FeesUpdated, WindowsUpdated, NewAssertion, NewVote, QuorumReached, SettledBounty, RevealedAssertion,
                Deprecated
            ]

            for cls in filter_events:
                self.filter_manager.register(cls, bounty_contract.eventFilter(cls.filter_event))

            self.filter_manager.register(LatestEvent, self.chain.w3.eth.filter('latest'))

            offer_registry_contract = self.chain.offer_registry.contract
            if offer_registry_contract:
                self.filter_manager.register(InitializedChannel, offer_registry_contract.eventFilter(cls.filter_event))

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
