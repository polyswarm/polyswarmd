import logging
from random import gauss
from typing import Any, Callable, Iterable, List, NoReturn, Set, Type

import gevent
from gevent.pool import Group
from gevent.queue import Queue
from requests.exceptions import ConnectionError

from . import messages

logger = logging.getLogger(__name__)


class ContractFilter:
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
Message = bytes
FilterInstaller = Callable[[str], ContractFilter]


class FilterWrapper:
    """A utility class which wraps a contract filter with websocket-messaging features"""
    filter: ContractFilter
    filter_installer = Callable[[], ContractFilter]
    formatter: FormatClass
    backoff: bool

    def __init__(self, filter_installer: FilterInstaller, formatter: FormatClass, backoff: bool):
        self.formatter = formatter
        self.backoff = backoff
        self._filter_installer = filter_installer
        self.filter = self.create_filter()

    def create_filter(self) -> ContractFilter:
        """Return a new filter

        NOTE: this function is here instead of directly assigned in __init__ to appease mypy"""
        installer: FilterInstaller = self._filter_installer
        return installer(self.formatter.contract_event_name)

    def compute_wait(self, ctr: int) -> float:
        """Compute the amount of wait time from a counter of (sequential) empty replies"""
        min_wait = 0.5
        max_wait = 4.0

        if self.backoff:
            # backoff 'exponentially'
            exp = (1 << max(0, ctr - 2)) - 1
            result = min(max_wait, max(min_wait, exp))
            return abs(gauss(result, 0.1))
        else:
            return min_wait

    def get_new_entries(self) -> List[Message]:
        return [self.formatter.serialize_message(e) for e in self.filter.get_new_entries()]

    def spawn_poll_loop(self, callback: Callable[[Iterable[Message]], NoReturn]):
        """Spawn a greenlet which polls the filter's contract events, passing results to `callback'"""
        ctr: int = 0  # number of loops since the last non-empty response
        wait: float = 0.0  # The amount of time this loop will wait.
        logger.debug("Spawning fetch: %s", self.filter)
        while True:
            ctr += 1
            # XXX spawn_later prevents easily killing the pool. Use `wait` here.
            gevent.sleep(wait)
            try:
                result = self.get_new_entries()
            # LookupError generally occurs when our schema doesn't match the message
            except LookupError:
                logger.exception("LookupError inside spawn_poll_loop")
                wait = 1
                continue
            # ConnectionError generally occurs when we cannot fetch events
            except (ConnectionError, TimeoutError):
                logger.exception("ConnectionError/timeout in spawn_poll_loop")
                wait = self.compute_wait(ctr)
                continue
            # ValueError generally occurs when Geth removed the filter
            except ValueError:
                logger.exception("Filter removed by Ethereum client")
                self.filter = self.create_filter()
                wait = 1
                continue

            # Reset the ctr if we received a non-empty response or we shouldn't backoff
            if len(result) != 0:
                ctr = 0
                callback(result)

            wait = self.compute_wait(ctr)
            logger.debug("%s wait=%f", self.filter, wait)


class FilterManager:
    """Manages access to filtered Ethereum events."""
    wrappers: Set[FilterWrapper]
    pool: Group

    def __init__(self):
        self.wrappers = set()
        self.pool = Group()

    def register(
        self, filter_installer: FilterInstaller, fmt_cls: FormatClass, backoff: bool = True
    ):
        """Add a new filter, with an optional associated WebsocketMessage-serializer class"""
        wrapper = FilterWrapper(filter_installer, fmt_cls, backoff)
        self.wrappers.add(wrapper)
        logger.debug('Registered new filter: %s', wrapper)

    def flush(self):
        """End all event polling, uninstall all filters and remove their corresponding wrappers"""
        self.pool.kill()
        self.wrappers.clear()

    def fetch(self):
        """Return a queue of currently managed contract events"""
        queue = Queue()
        for wrapper in self.wrappers:
            self.pool.spawn(wrapper.spawn_poll_loop, queue.put_nowait)
        yield from queue

    def setup_event_filters(self, chain: Any):
        """Setup the most common event filters"""
        if len(self.wrappers) != 0:
            logger.exception("Attempting to initialize already initialized filter manager")
            self.flush()

        bounty_contract = chain.bounty_registry.contract

        # Setup Latest (although this could pass `w3.eth.filter` directly)
        self.register(chain.w3.eth.filter, messages.LatestEvent.make(chain.w3.eth), backoff=False)
        # messages.NewBounty shouldn't wait or back-off from new bounties.
        self.register(bounty_contract.eventFilter, messages.NewBounty, backoff=False)

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
            self.register(bounty_contract.eventFilter, cls)

        offer_registry = chain.offer_registry
        if offer_registry and offer_registry.contract:
            self.register(offer_registry.contract.eventFilter, messages.InitializedChannel)
