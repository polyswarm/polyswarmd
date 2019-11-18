import logging
import weakref
from collections import namedtuple
from contextlib import contextmanager
from typing import Any, Callable, Collection, Container, Type
from random import gauss

from requests.exceptions import ConnectionError

import gevent
import web3.eth
from gevent.pool import Group
from gevent.queue import Queue
from web3.utils.filters import LogFilter

from . import messages

logger = logging.getLogger(__name__)


class FilterWrapper(namedtuple('Filter', ['filter', 'formatter', 'backoff'])):
    "A utility class which wraps a contract filter with websocket-messaging features"
    min_wait = 0.5
    max_wait = 8.0

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
        if self.filter.web3.eth.uninstallFilter(self.filter_id):
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
        ctr = 0
        wait = 0
        logger.debug("Spawning fetch: %s", self.contract_event_name())
        while True:
            try:
                # Spawn the next version of this instance
                gevent.sleep(wait)
                greenlet = gevent.spawn(self.get_new_entries)
                greenlet.link_value(callback)
                # NOTE there are pros and cons to leaving either gevent or wait logic inside the filter wrapper or the
                # manager. If someone can make a stronger case than "purity", or at least one stronger than the
                # associated additional work required to track waiting per-filter, I'm all ears -zv
                if len(greenlet.get()) == 0 and self.backoff:
                    ctr += 1
                else:
                    ctr = 0

                # backoff 'exponentially'
                exp = (1 << (ctr >> 2)) - 1
                wait = gauss(min(self.max_wait, max(self.min_wait, exp)), 0.1)
            except ConnectionError:
                wait = (wait + 1) * 2
                logger.exception('ConnectionError occurred')
            finally:
                logger.debug("%s wait=%f", self.contract_event_name(), wait)

    def __hash__(self):
        return hash(self.filter)


class FilterManager():
    """Manages access to filtered Ethereum events."""

    wrappers: Collection[FilterWrapper]
    pool: Group

    def __init__(self):
        self.wrappers = set()
        self.pool = Group()

    def register(self, flt: LogFilter, fmt_cls: Type[messages.EventLogMessage] = lambda x: x, backoff=True):
        "Add a new filter, with an optional associated WebsocketMessage-serializer class"
        wrapper = FilterWrapper(flt, fmt_cls, backoff)
        self.wrappers.add(wrapper)
        logger.debug('Registered new filter: %s', wrapper)

    def flush(self):
        self.pool.kill()
        logger.debug('Flushing filters.')
        for filt in self.wrappers:
            filt.uninstall()
        self.wrappers.clear()

    def setup_event_filters(self, chain):
        "Setup the most common event filters"
        # Setup Latest
        self.register(chain.w3.eth.filter('latest'), messages.LatestEvent.make(chain.w3.eth))

        bounty_contract = chain.bounty_registry.contract
        self.register(
            bounty_contract.eventFilter(messages.NewBounty.contract_event_name()),
            messages.NewBounty,
            # messages.NewBounty shouldn't wait or back-off from new bounties.
            backoff=False)

        filter_events = [
            messages.FeesUpdated, messages.WindowsUpdated, messages.NewAssertion, messages.NewVote,
            messages.QuorumReached, messages.SettledBounty, messages.RevealedAssertion, messages.Deprecated
        ]

        for cls in filter_events:
            self.register(bounty_contract.eventFilter(cls.contract_event_name()), cls)

        offer_registry = chain.offer_registry
        if offer_registry and offer_registry.contract:
            self.register(offer_registry.contract.eventFilter(messages.InitializedChannel.contract_event_name()),
                          messages.InitializedChannel)

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
            self.flush()
