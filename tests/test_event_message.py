from collections import UserList
from contextlib import contextmanager
from curses.ascii import EOT as END_OF_TRANSMISSION
import statistics
from string import ascii_lowercase
import time
from typing import ClassVar, Generator, Iterator, List, Mapping
import unittest.mock
import uuid

import gevent
from gevent.queue import Empty
import pytest
import ujson

from polyswarmd.services.ethereum.rpc import EthereumRpc
from polyswarmd.views.event_message import WebSocket
from polyswarmd.websockets.filter import (
    ContractFilter,
    FilterManager,
    FilterWrapper,
)
from polyswarmd.websockets.messages import WebsocketMessage

BEGIN = time.time()


def now():
    return int(1000 * (time.time() - BEGIN))


TX_TS = 'sent'
TXDIFF = 'interval'
CPUTIME = 'pipeline_latency'
START = 'start'
FILTER = 'filter'
STEP = 'step'
NTH = 'nth'
TICK = 'tick'

# How many 'ticks' should happen in a single step, allowing us to test more than one message being
# returned at one time
STRIDE = 10

# Generator for printable names used in debugging
FILTER_IDS = (l1 + l2 for l1 in ascii_lowercase for l2 in ascii_lowercase)


@pytest.fixture
def mock_sleep(monkeypatch):
    """If loaded, `gevent.sleep` simply returns a no-op unittest.Mock"""
    mock = unittest.mock.Mock(gevent.sleep)
    monkeypatch.setattr(gevent, "sleep", mock)
    return mock


@pytest.fixture
def rpc(monkeypatch):

    def patch(chain):
        RPC = EthereumRpc(chain)
        RPC.register = unittest.mock.Mock(wraps=RPC.register)
        RPC.unregister = unittest.mock.Mock(wraps=RPC.unregister)
        RPC.poll = unittest.mock.Mock(wraps=RPC.poll)
        RPC.filter_manager.setup_event_filters = unittest.mock.Mock(
            FilterManager.setup_event_filters
        )
        return RPC

    return patch


class NOPMessage(WebsocketMessage):
    """Stub for a polyswarmd.websocket.message object"""
    contract_event_name: ClassVar[str] = 'NOP_CONTRACT'
    event: ClassVar[str] = 'NOP_EVENT'


class MockFilter(ContractFilter):
    """Mock implementation of a Web3Py Filter.

    If no ``source`` generator is provided, it creates an event message generator running for for
    ``end`` "steps" and yielding ``1/rate`` messages on average.
    """

    def __init__(self, rate=1.0, source=None, end=100, backoff=False):
        # The rate at which this filter should generate new messages
        self.poll_interval = rate
        self.source = source or self.uniform(int(self.poll_interval * STRIDE), end=end)
        self.backoff = backoff

    def __call__(self, contract_event_name):
        # Verify that _something_ is being passed in, even if we're not using it.
        assert contract_event_name == NOPMessage.contract_event_name
        self.current = -1
        self.filter_id = next(FILTER_IDS)
        self.sent = 0
        self.start = now()
        return self

    def format_entry(self, step):
        return {FILTER: self.filter_id, NTH: self.sent, TX_TS: now(), START: self.start, STEP: step}

    def get_new_entries(self) -> Iterator:
        try:
            msgs = list(filter(None, [next(self.source) for i in range(STRIDE)]))
            yield from msgs
            self.sent += len(msgs)
        except StopIteration:
            raise gevent.GreenletExit

    def uniform(self, rate: int, end: int, offset=0) -> Generator:
        """Event message generator, runs for ``end`` steps, yielding ``1/rate`` messages each step"""
        for step in range(0, end * STRIDE):
            yield self.format_entry(step=step) if step % rate == 0 else None
        return step


class enrich(UserList):
    elapsed = property(lambda msgs: max(msgs[TX_TS]) - min(msgs[TX_TS]))
    steps = property(lambda msgs: [v for v in msgs[STEP] if v > 1e-1])
    responses = property(lambda msgs: len(msgs.steps))
    latency_var = property(lambda msgs: statistics.pvariance(msgs.steps))
    latency_avg = property(lambda msgs: statistics.mean(msgs.steps))
    usertime_avg = property(lambda msgs: statistics.mean(msgs[CPUTIME]))
    sources = property(lambda msgs: len(set(msgs[FILTER])))

    def __init__(self, messages, extra={}):
        self.data = list(self.enrich_messages(messages, extra))

    def enrich_messages(self, messages, extra={}):
        # ensure we've got some messages
        assert len(messages) > 0
        prev = {}
        for msg in map(ujson.loads, messages):
            # ensure we got an 'event' tag which should be included with all WebsocketMessage
            assert msg['event'] == NOPMessage.event
            emsg = msg['data']
            emsg[TX_TS] = emsg.get(TX_TS, -1)
            emsg[TXDIFF] = emsg[TX_TS] - prev.get(TX_TS, emsg[TX_TS])
            msg.update(extra)
            yield emsg
            prev = emsg

    def by_source(self):
        sources = {}
        for msg in self:
            sources[msg[FILTER]] = sources.get(msg[FILTER], []) + [msg]
        return sources

    def __getitem__(self, key):
        if isinstance(key, int):
            return super().__getitem__(key)
        return [msg[key] for msg in self.data]

    def __str__(self):
        props = ['elapsed', 'responses', 'usertime_avg']
        return '<%s summary=%s>' % (type(self), {k: getattr(self, k) for k in props})


class TestWebsockets:

    @contextmanager
    def start_rpc(self, filters, ws, RPC):
        RPC.register(ws)
        for ft in filters:
            RPC.filter_manager.register(ft, NOPMessage, backoff=ft.backoff)
        yield RPC
        RPC.unregister(ws)
        for mock in [RPC.poll, RPC.register, RPC.unregister, RPC.filter_manager.setup_event_filters]:
            mock.assert_called_once()
        assert len(RPC.filter_manager.pool) == 0
        assert len(RPC.websockets) == 0

    def events(self, filters, RPC, ws=None):
        """Mimic the behavior of ``/events`` endpoint

        Keep the implementation of this test as close as possible to
        `event_message.py#init_websockets#events(ws)`, e.g please do
        do not switch this to `join()` the pool, etc.

        If you find a way to use `Flask.test_client` with `Sockets`, please let me know - zv
        """
        ws = ws or WebSocket(str(uuid.uuid4()))
        with self.start_rpc(filters=filters, ws=ws, RPC=RPC):
            msgs = []
            while True:
                try:
                    msg = ws.queue.get(block=True, timeout=0)
                    msgs.append(msg)
                    # print(msg)
                except Empty:
                    break
            enriched = enrich(msgs)
            assert enriched.sources == len(filters)
            return enriched

    def test_recv(self, chains, rpc, mock_sleep):
        """
        - Verify that we can recieve messages through ``EthereumRPC``'s ``FilterManager``
        - The number of messages sent should equal the number of messages recieved
        """
        filters = [MockFilter(rate=1 / 2) for i in range(10)]
        enriched = self.events(filters=filters, RPC=rpc(chains))
        assert len(enriched) == sum(f.sent for f in filters)

    def test_concurrent_rpc(self, app, rpc, mock_sleep):
        """
        - Test multiple concurrent RPC & FilterManager instances:
        - Two ``EthereumRPC``, ``FilterManager`` & ``Websocket``s should be able to operate
          independently of one another on different chains"""
        rate = 1 / 2
        gs = gevent.joinall([
            gevent.spawn(
                self.events,
                filters=[MockFilter(rate=rate, end=100 + (1+i) * 50) for _ in range(2)],
                RPC=RPC
            ) for i, RPC in enumerate(map(rpc, app.config['POLYSWARMD'].chains.values()))
        ])
        # need good greenlets
        assert all(g.successful() for g in gs)
        ag, bg = map(lambda g: g.value, gs)
        # we should ahve gotten at least end * rate - 5 messages
        assert len(ag) >= 600
        # the second RPC ran for longer, therefore should have more messages
        assert len(bg) / len(ag) == 200 / 150

    def test_backoff(self, chains, rpc, mock_sleep):
        """
        - Validate filter-request backoff logic:
        - Filters with identical message intervals but differing in wait parameters should differ in
          the number of messages ultimately dispatched
        - We should automatically introduce random variance to prevent a large number of clients
          from simultaneous reconnects
        - Filters should never wait more than 30x their minimum wait time
        """
        rate = 11 / 2
        filters = [MockFilter(rate=rate * i, backoff=True, end=300) for i in range(1, 6)]
        enriched = self.events(filters=filters, RPC=rpc(chains))

        sleeps = [s for s in map(lambda x: x[0][0], mock_sleep.call_args_list)]
        rounded = set([round(s * 2) / 2 for s in sleeps])
        # we should never have a (base) wait time more than 10x larger than the smallest (nonzero) wait time
        assert min(filter(lambda x: x > 0, rounded)) * 10 > max(rounded)
        # we should be adding a random factor to each `compute_wait` output
        assert len(sleeps) > len(rounded)
        # We should see each of the wait periods (rounded to the nearest 0.5) at least once
        assert len(rounded) - 2 * (int(FilterWrapper.MAX_WAIT) - int(FilterWrapper.MIN_WAIT)) <= 1

        # verify that despite the backoff, sources with a higher rate churn out more events
        by_src = enriched.by_source()
        for i in range(len(filters) - 1):
            f, s = map(lambda idx: filters[idx].filter_id, (i, i + 1))
            assert len(by_src[f]) > len(by_src[s])
