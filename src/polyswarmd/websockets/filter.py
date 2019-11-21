import gevent
import logging
from collections import namedtuple
from contextlib import contextmanager
from gevent.pool import Group
from gevent.queue import Queue
from random import gauss
from requests.exceptions import ConnectionError
from typing import Collection, Type
from web3.utils.filters import LogFilter


from . import messages

logger = logging.getLogger(__name__)


class FilterWrapper(namedtuple('Filter', ['filter', 'formatter', 'backoff'])):
    """A utility class which wraps a contract filter with websocket-messaging features"""
    MIN_WAIT = 0.5
    MAX_WAIT = 8.0

    @property
    def ws_event(self):
        """"Return the name of the websocket 'event name' that events will be formatted with"""
        return self.formatter.ws_event if self.formatter else 'N/A'

    @property
    def filter_id(self):
        """Return the associated contract event filter's numeric web3 id"""
        return self.filter.filter_id

    def contract_event_name(self):
        """Return the name of the associated contract event."""
        return self.formatter.contract_event_name() if self.formatter else 'Unknown'

    def uninstall(self):
        if self.filter.web3.eth.uninstallFilter(self.filter_id):
            logger.debug("Uninstalled filter_id=%s", self.filter_id)
        else:
            logger.warning("Could not uninstall filter<filter_id=%s>")

    def compute_wait(self, ctr):
        """Compute the amount of wait time from a counter of (sequential) empty replies"""
        if self.backoff:
            # backoff 'exponentially'
            exp = (1 << max(0, ctr - 2)) - 1
            result = min(self.MAX_WAIT, max(self.MIN_WAIT, exp))
        else:
            result = self.MIN_WAIT

        return abs(gauss(result, 0.1))

    def get_new_entries(self):
        return [self.formatter(e) for e in self.filter.get_new_entries()]

    def spawn_poll_loop(self, callback):
        """Spawn a greenlet which polls the filter's contract events, passing results to `callback'"""
        ctr = 0  # number of loops since the last non-empty response
        wait = 0  # The amount of time this loop will wait.
        logger.debug("Spawning fetch: %s", self.contract_event_name())
        while True:
            ctr += 1
            # XXX spawn_later prevents easily killing the pool. Use `wait` here.
            gevent.sleep(wait)
            # Spawn the next version of this instance
            greenlet = gevent.spawn(self.get_new_entries)
            try:
                result = greenlet.get(block=True, timeout=self.MAX_WAIT)
            # KeyError generally arises when the JSONSchema describing a message is fed an invalid value.
            except KeyError as e:
                logger.exception(e)
                continue
            # ConnectionError generally occurs when we cannot fetch events
            except (ConnectionError, gevent.Timeout):
                logger.exception("Error thrown in get_new_entries")
                wait = self.compute_wait(ctr + 2)
                continue

            # Reset the ctr if we recieved a non-empty response or we shouldn't backoff
            if len(result) != 0:
                callback(result)
                ctr = 0

            # We add gaussian randomness so that requests are queued all-at-once.
            wait = self.compute_wait(ctr)
            logger.debug("%s wait=%f", self.contract_event_name(), wait)

    def __hash__(self):
        return hash(self.filter)


class FilterManager:
    """Manages access to filtered Ethereum events."""

    wrappers: Collection[FilterWrapper]
    pool: Group

    def __init__(self):
        self.wrappers = set()
        self.pool = Group()

    def register(self, fltr: LogFilter, fmt_cls: Type[messages.EventLogMessage] = lambda x: x, backoff=True):
        """Add a new filter, with an optional associated WebsocketMessage-serializer class"""
        wrapper = FilterWrapper(fltr, fmt_cls, backoff)
        self.wrappers.add(wrapper)
        logger.debug('Registered new filter: %s', wrapper)

    def flush(self):
        """"End all event polling, uninstall all filters and remove their corresponding wrappers"""
        self.pool.kill()
        logger.debug('Flushing %d filters', len(self.wrappers))
        for filt in self.wrappers:
            filt.uninstall()
        self.wrappers.clear()

    @contextmanager
    def fetch(self):
        """Return a queue of currently managed contract events"""
        try:
            queue = Queue()
            # Greenlet's can continue to exist beyond the lifespan of
            # the object itself. Failing to use a weakref here can prevent filters
            # destructors from running
            for wrapper in self.wrappers:
                self.pool.spawn(wrapper.spawn_poll_loop, queue.put_nowait)

            yield queue
        finally:
            self.flush()

    def setup_event_filters(self, chain):
        """"Setup the most common event filters"""
        if len(self.wrappers) != 0:
            logger.exception("Attempting to initialize already initialized filter manager")
            return

        # Setup Latest
        self.register(chain.w3.eth.filter('latest'), messages.LatestEvent.make(chain.w3.eth), backoff=False)

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
