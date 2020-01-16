from dataclasses import dataclass, field
from math import ceil
import time
from typing import Any, List

import gevent
from gevent.queue import Empty
import pytest

from polyswarmd.services.ethereum.rpc import EthereumRpc
from polyswarmd.views.event_message import WebSocket
from polyswarmd.websockets.filter import FilterManager

current = time.monotonic

MAX_WAIT = 4


def elapsed(since):
    return current() - since


def read_wrapper_queue(filters, wrapper, ethrpc, wait=MAX_WAIT):
    ethrpc.register(wrapper)
    for filt in filters:
        ethrpc.filter_manager.register(DumbFilter(**filt), MockFormatter)

    start = current()
    msgs = []
    while elapsed(since=start) < wait:
        try:
            obj = wrapper.queue.get(block=True, timeout=1)
            msgs.append(obj)
        except Empty:
            pass
    ethrpc.unregister(wrapper)
    return msgs


def test_recv(mock_fm, wrapper, rpc):
    wait = MAX_WAIT
    speed = 0.25
    results = read_wrapper_queue(filters=[dict(speed=speed)], wrapper=wrapper, ethrpc=rpc, wait=wait)
    times = [r.get('current') for r in results]
    count = wait / speed
    assert pytest.approx((max(times) - min(times), count))
    assert pytest.approx((len(results), count))


def test_concurrent_rpc(mock_fm, mock_ws):
    # verify that multiple engines can run concurrently
    outst = [
        gevent.spawn(
            read_wrapper_queue,
            filters=[dict()],
            wrapper=WebSocket('N/A'),
            ethrpc=EthereumRpc('n/a')
        ),
        gevent.spawn(
            read_wrapper_queue,
            filters=[dict()],
            wrapper=WebSocket('N/A'),
            ethrpc=EthereumRpc('n/a')
        )
    ]
    vz = list(map(lambda k: k.value, gevent.joinall(outst)))
    assert len(vz) == len(outst)
    assert all(len(vz[0]) == len(v) for v in vz)


@dataclass
class DumbFilter:
    speed: float = field(default=1.0)
    start: float = field(default_factory=current)
    last: int = field(default=-1)
    attach: Any = field(default=None)

    def __call__(self, contract_event_name):
        return self

    def to_msg(self, idx):
        return {
            **{k: v for k, v in self.__dict__.items() if bool(v)},
            'idx': idx,
            'current': current(),
        }

    def get_new_entries(self):
        last = self.last
        nxt = ceil(elapsed(self.start) / self.speed)
        self.last = nxt
        yield from map(self.to_msg, range(last, nxt))


class MockFormatter:
    contract_event_name = str(None)

    @classmethod
    def serialize_message(cls, e):
        return e


@pytest.fixture
def mock_ws(monkeypatch):
    """Requests.get() mocked to return {'mock_key':'mock_response'}."""

    def mock_send(self, msg):
        self.queue.put_nowait(msg)

    monkeypatch.setattr(WebSocket, "send", mock_send)


@pytest.fixture
def mock_fm(monkeypatch):
    """Requests.get() mocked to return {'mock_key':'mock_response'}."""

    def mock_setup_event_filters(self, chain):
        return True

    monkeypatch.setattr(FilterManager, "setup_event_filters", mock_setup_event_filters)


@pytest.fixture
def wrapper(mock_ws):
    """Requests.get() mocked to return {'mock_key':'mock_response'}."""
    return WebSocket('ws: N/A')


@pytest.fixture
def rpc(chains):
    return EthereumRpc(chains)
