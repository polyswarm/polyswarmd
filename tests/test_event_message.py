import pytest
import time
from polyswarmd.websockets.filter import FilterManager
from polyswarmd.services.ethereum.rpc import EthereumRpc
from polyswarmd.views.event_message import WebSocket
from gevent.queue import Empty

MAX_WAIT = 10
current = time.monotonic


def elapsed(start=current()):
    return current() - start


def test_recv(mock_fm, wrapper, rpc):
    rpc.register(wrapper)
    rpc.filter_manager.register(lambda *args: DumbFilter(speed=1), MockFormatter)
    while True:
        try:
            msg = wrapper.queue.get(block=True, timeout=MAX_WAIT // 2)
            assert msg is not None
        except Empty:
            break
    rpc.unregister(wrapper)


class DumbFilter:
    def __init__(self, expected_msgs=[], speed=1):
        self.expected_msgs = expected_msgs
        self.speed = speed
        self.start = current()
        self.last = 0

    @property
    def expected(self):
        if self.expected_msgs:
            yield from self.expected_msgs
        else:
            yield from [{'speed': self.speed, 'idx': i, 'when': current()}
                        for i in range(MAX_WAIT // self.speed)]

    def get_new_entries(self):
        last = self.last
        current = int(self.speed * elapsed(self.start))
        expected = list(self.expected)
        self.last = current
        return expected[last:current]


class MockFormatter:
    contract_event_name = str(None)

    @classmethod
    def serialize_message(cls, e):
        return e


@pytest.fixture
def mock_ws(monkeypatch):
    """Requests.get() mocked to return {'mock_key':'mock_response'}."""
    def mock_send(self, msg):
        print(msg)

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
