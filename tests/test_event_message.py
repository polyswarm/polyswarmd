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


def read_wrapper_queue(filters, wrapper=WebSocket('N/A'), ethrpc=None, wait=MAX_WAIT, backoff=False):
    ethrpc.register(wrapper)
    for filt in filters:
        ethrpc.filter_manager.register(DumbFilter(**filt), MockFormatter, backoff=backoff)

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


def test_SLOW_recv(chains, wrapper, rpc):
    wait = 2
    speed = 0.5
    results = read_wrapper_queue(filters=[dict(speed=speed)], wrapper=wrapper, ethrpc=rpc(chains), wait=wait)
    times = [r.get('current') for r in results]
    count = wait / speed
    assert pytest.approx((max(times) - min(times), count))
    assert pytest.approx((len(results), count))


def test_SLOW_concurrent_rpc(homechain, sidechain, mock_fm, mock_ws, rpc):
    # verify that multiple engines can run concurrently
    # run them at different times to verify that disconnecting
    # one doesn't affect the other.
    fwait, lwait = 4, 8
    fst, last = [
        gevent.spawn(
            read_wrapper_queue,
            filters=[dict()],
            wait=fwait,
            ethrpc=rpc(homechain)
        ),
        gevent.spawn(
            read_wrapper_queue,
            filters=[dict()],
            wait=lwait,
            ethrpc=rpc(sidechain)
        ),
    ]
    fr, lr = (k.value for k in gevent.joinall((fst, last)))
    assert len(fr) < len(lr)
    assert len(fr) > 0 and len(lr) > 0
    assert pytest.approx((len(fr), len(lr) * (fwait // lwait)))


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
        # print(msg)
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
def rpc(mock_fm):
    return EthereumRpc
