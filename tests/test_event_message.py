from contextlib import contextmanager
from dataclasses import dataclass, field
from math import ceil
import time
from typing import Any, ClassVar, Optional

import statistics
import gevent
from gevent.queue import Empty
import pytest

from polyswarmd.services.ethereum.rpc import EthereumRpc
from polyswarmd.views.event_message import WebSocket
from polyswarmd.websockets.filter import FilterManager
from polyswarmd.websockets.messages import (
    ClosedAgreement,
    Connected,
    SettleStateChallenged,
    StartedSettle,
    WebsocketFilterMessage,
)

current = time.monotonic


def elapsed(since):
    return current() - since


class TestWebsockets:

    @contextmanager
    def start_rpc(self, filters, ws, RPC, backoff):
        RPC.register(ws)
        for ft in filters:
            RPC.filter_manager.register(ft, FakeFormatter, backoff=backoff)
        yield RPC
        RPC.unregister(ws)
        assert len(RPC.websockets) == 0

    def rq(self, filters, ws, RPC, max_wait=3, backoff=False, timeout=1):
        start = current()
        count = int(sum(max_wait // f.speed for f in filters))

        with self.start_rpc(filters=filters, ws=ws, RPC=RPC, backoff=backoff):
            msgs = []
            while elapsed(since=start) < max_wait:
                try:
                    msgs.append(ws.queue.get(block=True, timeout=timeout))
                except Empty:
                    continue
            # the number of msgs should be ~ (elapsed_time / msg_rate) * num_of_msg_srcs)
            assert abs(len(msgs) - count) <= 1
            return msgs

    @pytest.mark.parametrize("chains", ['home'])
    def test_SLOW_recv(self, chains, wrapper, rpc):
        max_wait = 3
        speed = 0.5
        filters = [DumbFilter(speed=speed) for _ in range(3)]
        results = self.rq(filters=filters, ws=wrapper, max_wait=max_wait, RPC=rpc(chains))
        # we should have at least 1 results
        assert len(results) > 0
        # verify the time elapsed took what we thought
        times = [r.get('current') for r in results]
        assert abs(max(times) - min(times) - max_wait) < 0.5
        # verify that the average time was what we expected
        diff = [times[i] - times[i - 1] for i in range(1, len(times))]
        assert abs(statistics.pvariance(diff) - speed) < 0.5

    def test_SLOW_concurrent_rpc(self, app, mock_fm, mock_ws, rpc):
        # verify that multiple engines can run concurrently
        # run them at different times to verify that disconnecting
        # one doesn't affect the other.
        chains = ((app.config['POLYSWARMD'].chains[c]) for c in ('home', 'side'))
        base_wait = 4
        gs = gevent.joinall([
            gevent.spawn(
                self.rq,
                filters=[DumbFilter(speed=0.5)],
                ws=WebSocket(f'N{i + 1}'),
                max_wait=base_wait * (1+i),
                RPC=rpc(chain)
            ) for i, chain in enumerate(chains)
        ])

        for i in range(len(gs)):
            assert gs[i].successful()
            a = len(gs[i].value)
            assert a >= 1
            if len(gs) > a:
                b = len(gs[i + 1].value)
                assert a < b + 1e-5
                assert pytest.approx((a, b * ((i+1) * base_wait) / ((i+2) * base_wait)), abs=1)

    @pytest.mark.parametrize("chains", ['home'])
    def test_SLOW_backoff(self, chains, wrapper, rpc):
        results = self.rq(
            filters=[DumbFilter(speed=1) for _ in range(3)],
            ws=wrapper,
            RPC=rpc(chains),
            backoff=True
        )
        assert len(results) > 0


@dataclass
class DumbFilter:
    speed: float = field(default=1.0)
    prev: int = field(default=0)
    attach: Any = field(default=None)
    start: Optional[float] = field(default=None)

    # Verify that _something_ is being passed in, even if we're not using it.
    def __call__(self, contract_event_name):
        return self

    def to_msg(self, idx):
        return {**self.__dict__, 'idx': idx, 'current': current()}

    def get_new_entries(self):
        if not self.start:
            self.start = current()
        prev = self.prev
        curr = ceil(elapsed(self.start) / self.speed)
        self.prev = curr
        yield from map(self.to_msg, range(prev, curr))


class FakeFormatter:
    contract_event_name: ClassVar[str] = str(None)

    @classmethod
    def serialize_message(cls, data):
        return data


@pytest.fixture
def mock_ws(monkeypatch):

    def mock_send(self, msg):
        # print(msg)
        self.queue.put_nowait(msg)

    monkeypatch.setattr(WebSocket, "send", mock_send)


@pytest.fixture
def mock_fm(monkeypatch):
    monkeypatch.setattr(FilterManager, "setup_event_filters", lambda *_: True)


@pytest.fixture(scope='function')
def wrapper(mock_ws):
    return WebSocket('ws: N/A')


@pytest.fixture
def rpc(mock_fm):
    return EthereumRpc
