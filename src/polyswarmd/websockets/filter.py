import logging
import weakref
from contextlib import contextmanager
from random import gauss
from typing import Callable, Iterable, NoReturn, Set, Any, Type, List

from requests.exceptions import ConnectionError

import gevent
from gevent.pool import Group
from gevent.queue import Queue

from . import messages

logger = logging.getLogger(__name__)


class ContractFilter():
    callbacks: List[Callable[..., Any]]
    stopped: bool
    poll_interval: float
    filter_id: int
    web3: Any

    def get_new_entries(self) -> List[messages.EventData]:
        ...

    def get_all_entries(self) -> List[messages.EventData]:
        ...


FormatClass = Type[messages.WebsocketFilterMessage]
Message = messages.WebsocketMessage


class FilterWrapper:
    "A utility class which wraps a contract filter with websocket-messaging features"
    filter: ContractFilter
    formatter: FormatClass
    backoff: bool

    __slots__ = ('filter', 'formatter', 'backoff')

    def __init__(self, fltr: ContractFilter, formatter: FormatClass, backoff: bool):
        self.filter = fltr
        self.formatter = formatter
        self.backoff = backoff

    @property
    def filter_id(self) -> int:
        """Return the associated contract event filter's numeric web3 id"""
        return self.filter.filter_id

    def uninstall(self):
        if self.filter.web3.eth.uninstallFilter(self.filter_id):
            logger.debug("Uninstalled filter_id=%s", self.filter_id)
        else:
            logger.warn("Could not uninstall filter<filter_id=%s>")

    def compute_wait(self, ctr: int) -> float:
        """Compute the amount of wait time from a counter of (sequential) empty replies"""
        min_wait = 0.5
        max_wait = 8.0

        result: float = 1.0
        if self.backoff:
            # backoff 'exponentially'
            exp = (1 << max(0, ctr - 2)) - 1
            result = min(max_wait, max(min_wait, exp))
        else:
            result = min_wait

        return abs(gauss(result, 0.1))

    def get_new_entries(self) -> Iterable[Message]:
        return [self.formatter(e) for e in self.filter.get_new_entries()]

    def spawn_poll_loop(self, callback: Callable[[Iterable[FormatClass]], NoReturn]):
        """Spawn a greenlet which polls the filter's contract events, passing results to `callback'"""
        ctr: int = 0  # number of loops since the last non-empty response
        wait: float = 0.0  # The amount of time this loop will wait.
        logger.debug("Spawning fetch: %s", self.filter)
        while True:
            ctr += 1
            # XXX spawn_later prevents easily killing the pool. Use `wait` here.
            gevent.sleep(wait)
            # Spawn the next version of this instance
            greenlet = gevent.spawn(self.get_new_entries)
            try:
                result = greenlet.get(block=True, timeout=120.0)
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
                ctr = 0
                callback(result)

            # We add gaussian randomness so that requests are queued all-at-once.
            wait = self.compute_wait(ctr)
            logger.debug("%s wait=%f", self.filter, wait)


class FilterManager():
    """Manages access to filtered Ethereum events."""

    wrappers: Set[FilterWrapper]
    pool: Group

    def __init__(self):
        self.wrappers = set()
        self.pool = Group()

    def register(self, fltr: ContractFilter, fmt_cls: FormatClass, backoff: bool = True):
        """Add a new filter, with an optional associated WebsocketMessage-serializer class"""
        wrapper = FilterWrapper(fltr, fmt_cls, backoff)
        self.wrappers.add(wrapper)
        logger.debug('Registered new filter: %s', wrapper)

    def flush(self):
        """End all event polling, uninstall all filters and remove their corresponding wrappers"""
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
            for wrapper in map(weakref.proxy, self.wrappers):
                self.pool.spawn(wrapper.spawn_poll_loop, queue.put_nowait)

            yield queue
        finally:
            self.flush()

    def setup_event_filters(self, chain: Any):
        """Setup the most common event filters"""
        if len(self.wrappers) != 0:
            logger.exception("Attempting to initialize already initialized filter manager")
            return

        # Setup Latest
        self.register(chain.w3.eth.filter('latest'), messages.LatestEvent.make(chain.w3.eth), backoff=False)

        bounty_contract = chain.bounty_registry.contract
        self.register(
            bounty_contract.eventFilter(messages.NewBounty.contract_event_name),
            messages.NewBounty,
            # messages.NewBounty shouldn't wait or back-off from new bounties.
            backoff=False)

        filter_events = [
            messages.FeesUpdated, messages.WindowsUpdated, messages.NewAssertion, messages.NewVote,
            messages.QuorumReached, messages.SettledBounty, messages.RevealedAssertion, messages.Deprecated
        ]

        for cls in filter_events:
            self.register(bounty_contract.eventFilter(cls.contract_event_name), cls)

        offer_registry = chain.offer_registry
        if offer_registry and offer_registry.contract:
            self.register(
                offer_registry.contract.eventFilter(messages.InitializedChannel.contract_event_name),
                messages.InitializedChannel)
