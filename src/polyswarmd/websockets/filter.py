import logging
import weakref
from collections import namedtuple
from typing import Any, Callable, Collection, Container, Type

from requests.exceptions import ConnectionError

import gevent
import web3.eth
from gevent.pool import Pool
from web3.utils.filters import LogFilter
from .messages import (Deprecated, FeesUpdated, InitializedChannel, LatestEvent, NewAssertion, NewBounty, NewVote,
                       QuorumReached, RevealedAssertion, SettledBounty, WindowsUpdated, EventLogMessage)

logger = logging.getLogger(__name__)


class FilterWrapper(namedtuple('Filter', ['filter', 'formatter', 'wait'])):
    "A utility class which wraps a contract filter with websocket-messaging features"

    def get_new_entries(self):
        for entry in self.filter.get_new_entries():
            yield self.formatter(entry)

    @property
    def ws_event(self):
        return self.formatter.ws_event if self.formatter else 'N/A'

    def contract_event_name(self):
        return self.formatter.contract_event_name() if self.formatter else 'Unknown'

    def __del__(self):
        web3.eth.uninstallFilter(self.filter.filter_id)
        super().__del__(self)

    def __hash__(self):
        return hash(self.filter)

class FilterManager():
    """Manages access to filtered Ethereum events."""

    wrappers: Collection[FilterWrapper]
    pool: Pool
    MIN_WAIT: float = 0.1
    MAX_WAIT: float = 10.0

    def __init__(self):
        self.wrappers = set()
        self.pool = Pool(None)

    def register(self, flt: LogFilter, fmt_cls: Type[EventLogMessage] = lambda x: x, wait=1):
        "Add a new filter, with an optional associated WebsocketMessage-serializer class"
        wrapper = FilterWrapper(flt, fmt_cls, wait)
        self.wrappers.add(wrapper)
        logger.debug('Registered new filter: %s', wrapper)
        self.pool.size = (len(self.wrappers) * 2) + 1

    def __del__(self):
        "Destructor to be run when a filter manager is no longer needed"
        self.pool.kill()
        super().__del__(self)

    def flush(self):
        logger.debug('Clearing out of date filter events.')
        for filt in self.filters:
            filt.get_new_entries()

    def setup_event_filters(self, chain):
        "Setup the most common event filters"
        # Setup Latest
        self.register(chain.w3.eth.filter('latest'), LatestEvent.make(chain.w3.eth))

        bounty_contract = chain.bounty_registry.contract
        self.register(
            bounty_contract.eventFilter(NewBounty.contract_event_name()),
            NewBounty,
            # NewBounty shouldn't wait or back-off from new bounties.
            wait=0)

        filter_events = [
            FeesUpdated, WindowsUpdated, NewAssertion, NewVote, QuorumReached, SettledBounty, RevealedAssertion,
            Deprecated
        ]

        for cls in filter_events:
            self.register(bounty_contract.eventFilter(cls.contract_event_name()), cls)

        offer_registry = chain.offer_registry
        if offer_registry and offer_registry.contract:
            self.register(offer_registry.contract.eventFilter(InitializedChannel.contract_event_name()),
                          InitializedChannel)

    def event_pool(self, callback: Callable[..., Any], immediate: Container[LogFilter] = {NewBounty}):
        """Maintains a gevent Pool of filter event entry fetchers.

        The pool is filled by `fetch_filter', which automatically creates
        another greenlet of itself. It may also alter how long it waits before
        that greenlet is run based on if:

            - No entries were returned by this filter (it doesn't need to be checked as frequently)
            - A connection error occurred (maybe geth is down, try to back off and wait)
        """
        def fetch_filter(wrapper: FilterWrapper, wait: int):
            try:
                # XXX This is YAGNI here, but it might make sense to break out
                # wait and result-handling logic into a function which is passed
                # in by the caller to `event_pool'
                handled = 0
                for entry in wrapper.get_new_entries():
                    callback(entry)
                    handled += 1
                if wait:
                    if handled == 0:
                        wait *= 2  # if there's no traffic, back off
                    elif wait > self.MAX_WAIT // 2:
                        wait //= 2  # but drop quickly if our wait is high w/ new traffic
                    elif wait > 1:
                        wait -= 1  # otherwise steadily decrease
                    elif handled > 1 and wait > 0.1:
                        wait -= 0.1
            except ConnectionError:
                if wait:
                    wait = (wait + 1) * 2
                    logger.exception('ConnectionError occurred, backing off...')

            # Spawn the next version of this instance
            if wait:
                wait = min(self.MAX_WAIT, max(self.MIN_WAIT, wait))
                logger.debug("%s wait: %f", wrapper.contract_event_name(), wait)
            self.pool.start(gevent.spawn_later(max(wait, self.MIN_WAIT), fetch_filter, wrapper, wait))

        # Greenlet's can continue to exist beyond the lifespan of
        # the object itself. Failing to use a weakref here can prevent filters
        # destructors from running
        for wrapper in map(weakref.proxy, self.wrappers):
            logger.debug("Spawning filter: %s", wrapper.contract_event_name())
            self.pool.spawn(fetch_filter, wrapper, wrapper.wait)

        return self.pool
