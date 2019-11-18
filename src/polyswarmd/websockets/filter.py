import logging
import weakref
from collections import namedtuple
from contextlib import contextmanager
from typing import Any, Callable, Collection, Container, Type
from random import random

from requests.exceptions import ConnectionError

import gevent
import web3.eth
from gevent.pool import Group
from gevent.queue import Queue
from web3.utils.filters import LogFilter

from .messages import (Deprecated, EventLogMessage, FeesUpdated, InitializedChannel, LatestEvent, NewAssertion,
                       NewBounty, NewVote, QuorumReached, RevealedAssertion, SettledBounty, WindowsUpdated)

logger = logging.getLogger(__name__)


class FilterWrapper(namedtuple('Filter', ['filter', 'formatter', 'wait'])):
    "A utility class which wraps a contract filter with websocket-messaging features"
    min_wait = 0.2
    max_wait = 10.0
    __slots__ = ('filter', 'formatter', 'backoff')

    def __init__(self, filter, formatter, backoff):
        self.filter = filter
        self.formatter = formatter
        self.backoff = backoff

    @property
    def ws_event(self):
        "Return the name of the websocket 'event name' that events will be formatted with"
        return self.formatter.ws_event if self.formatter else 'N/A'

    @property
    def filter_id(self):
        "Return the associated contract event filter's numeric web3 id"
        return self.filter.filter_id

    def contract_event_name(self):
        "Return the name of the associated contract event."
        return self.formatter.contract_event_name() if self.formatter else 'Unknown'

    def uninstall(self):
        "Uninstall this filter. We will no longer recieve changes"
        logger.debug("%s destructor preparing to run", repr(self))
        if web3.eth.uninstallFilter(self.filter_id):
            logger.debug("Uninstalled filter<filter_id=%s>", self.filter_id)
        else:
            logger.warn("Could not uninstall filter<filter_id=%s>")

    def __del__(self):
        self.uninstall()
        super().__del__(self)

    def get_new_entries(self):
        return [self.formatter(entry) for entry in self.filter.get_new_entries()]

    def spawn_poll_loop(self, callback):
        "Spawn a greenlet which polls the filter's contract events, passing results to `callback'"
        shift = 0
        wait = 0
        logger.debug("Spawning fetch: %s", self.contract_event_name())
        while True:
            try:
                # Spawn the next version of this instance
                greenlet = gevent.spawn_later(wait, self.get_new_entries)
                greenlet.link_value(callback)
                entries = greenlet.get()
                # NOTE there are pros and cons to leaving either gevent or wait logic inside the filter wrapper or the
                # manager. If someone can make a stronger case than "purity", or at least one stronger than the
                # associated additional work required to track waiting per-filter, I'm all ears -zv
                if len(entries) == 0 and self.backoff:
                    shift += 1
                else:
                    shift = 0

                # backoff 'exponentially'
                wait = min(self.max_wait, max(self.min_wait, random() + (1 << (shift >> 2)) - 1))
            except ConnectionError:
                wait = (wait + 1) * 2
                logger.exception('ConnectionError occurred')
            finally:
                logger.debug("%s wait=%f", self.contract_event_name(), min(self.min_wait, wait))

    def __hash__(self):
        return hash(self.filter)


class FilterManager():
    """Manages access to filtered Ethereum events."""

    wrappers: Collection[FilterWrapper]
    pool: Group

    def __init__(self):
        self.wrappers = set()
        self.pool = Group()

    def register(self, flt: LogFilter, fmt_cls: Type[EventLogMessage] = lambda x: x, backoff=True):
        "Add a new filter, with an optional associated WebsocketMessage-serializer class"
        wrapper = FilterWrapper(flt, fmt_cls, backoff)
        self.wrappers.add(wrapper)
        logger.debug('Registered new filter: %s', wrapper)

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
            backoff=False)

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

    @contextmanager
    def fetch(self):
        "Return a queue of currently managed contract events"
        try:
            queue = Queue()
            # Greenlet's can continue to exist beyond the lifespan of
            # the object itself. Failing to use a weakref here can prevent filters
            # destructors from running
            for wrapper in map(weakref.proxy, self.wrappers):
                self.pool.spawn(wrapper.spawn_poll_loop, queue.put_nowait)

            yield queue
        finally:
            self.pool.kill()
            self.wrappers.clear()
