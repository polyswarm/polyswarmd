from collections.abc import Collection
from contextlib import contextmanager
from dataclasses import dataclass, field
from math import ceil
from operator import itemgetter as iget
import pprint
import statistics
import time
from typing import Any, ClassVar, List, Mapping, Optional

import gevent
from gevent.queue import Empty
import pytest
import ujson

from polyswarmd.services.ethereum.rpc import EthereumRpc
from polyswarmd.views.event_message import WebSocket
from polyswarmd.websockets.filter import FilterManager
from polyswarmd.websockets.messages import (
    ClosedAgreement,
    Connected,
    SettleStateChallenged,
    StartedSettle,
    WebsocketEventMessage,
    WebsocketFilterMessage,
    WebsocketMessage,
)

now = time.time
BEGIN = now()
WHEN = 'time'
TX_TS = 'sent'
RX_TS = 'recieved'
TXDIFF = 'interval'
CPUTIME = 'pipeline_latency'
MAXWAIT = 'max_wait'
BACKOFF = 'backoff'
START = 'start'
FILTERID = 'filter'
NTH = 'nth'


def elapsed(since):
    return now() - since


class NOPMessage(WebsocketMessage):
    contract_event_name: ClassVar[str] = 'test'
    event: ClassVar[str] = 'nop'


@dataclass
class DumbFilter:
    speed: float = field(default=1.0)
    prev: int = field(default=0)
    extra: Any = field(default_factory=dict)
    start: Optional[float] = field(default=None)

    # Verify that _something_ is being passed in, even if we're not using it.
    def __call__(self, contract_event_name):
        return self

    def to_msg(self, idx):
        return {FILTERID: id(self), NTH: idx, TX_TS: now(), 'speed': self.speed, START: self.start}

    def get_new_entries(self):
        if not self.start:
            self.start = now()
        prev = self.prev
        curr = ceil(elapsed(self.start) / self.speed)
        yield from map(self.to_msg, range(prev, curr))
        self.prev = curr


class enrich(Collection):
    msgs: List[Mapping] = []

    def __init__(self, messages, extra={}):
        prev = {}
        for msg in messages:
            data = msg.get('data', {})
            del msg['data']
            msg[FILTERID] = data.get(FILTERID, -1)
            msg[NTH] = data.get(NTH, -1)
            msg[TX_TS] = data.get(TX_TS, -1)
            msg[TXDIFF] = msg[TX_TS] - prev.get(TX_TS, msg[TX_TS])
            msg[CPUTIME] = now() - msg[TX_TS]
            if extra:
                msg.update(extra)
            self.msgs.append(msg)
            prev = msg

    def __iter__(self):
        return iter(self.msgs)

    def __contains__(self, o):
        return o in self.msgs

    def __len__(self):
        return len(self.msgs)

    def __str__(self):
        props = ['elapsed', 'responses', 'latency_var', 'latency_avg', 'usertime_avg']
        return f'{type(self)}=[{self.msgs[0:3]}...]\n' + pprint.pformat({
            k: getattr(self, k) for k in props
        })

    def mx(self, key):
        return map(iget(key), self)

    @property
    def elapsed(self):
        return max(self.mx(TX_TS)) - min(self.mx(TX_TS))

    @property
    def bundles(self):
        return [v for v in self.mx(TXDIFF) if v > 1e-1]

    @property
    def responses(self):
        return len(self.bundles)

    @property
    def latency_var(self):
        return statistics.pvariance(self.bundles)

    @property
    def latency_avg(self):
        return statistics.mean(self.bundles)

    @property
    def usertime_avg(self):
        return statistics.mean(self.mx(CPUTIME))

    @property
    def sources(self):
        return len(set(self.mx()))


class TestWebsockets:

    @contextmanager
    def start_rpc(self, filters, ws, RPC, backoff):
        RPC.register(ws)
        for ft in filters:
            RPC.filter_manager.register(ft, NOPMessage, backoff=backoff)
        yield RPC
        RPC.unregister(ws)
        assert len(RPC.websockets) == 0

    def events(self, filters, ws, RPC, max_wait=3, backoff=False, timeout=1):
        """Mimic the behavior of /events endpoint for tests"""

        # NOTE: KEEP IMPL CLOSE TO `event_message.py#init_websockets#events(ws)`
        # I wasn't able to find how to use a Flask app client with `Sockets` without
        # making some changes to how `init_websockets` works, so this function
        # just reproduces that behavior in this testable environment, please let
        # met know if you've figured out a way around this -zv
        start = now()

        with self.start_rpc(filters=filters, ws=ws, RPC=RPC, backoff=backoff):
            msgs = []
            while elapsed(since=start) < max_wait:
                try:
                    msg = ws.queue.get(block=True, timeout=timeout)
                    msgs.append(msg)
                    # print(msg)
                except Empty:
                    continue
            return enrich(msgs)

    @pytest.mark.parametrize("chains", ['home'])
    def test_SLOW_recv(self, chains, wrapper, rpc):
        """Verify that we can recieve msgs with uniform timing"""
        max_wait = 3
        speed = 0.5
        filters = [DumbFilter(speed=speed) for _ in range(3)]
        count = int(sum(max_wait // f.speed for f in filters))
        enrc = self.events(filters=filters, ws=wrapper, max_wait=max_wait, RPC=rpc(chains))
        # just to be sure
        assert len(enrc) > 0
        # the number of msgs should be ~ (elapsed_time / msg_rate) * num_of_msg_srcs)
        assert abs(len(enrc) - count) <= 1
        # verify the time elapsed took what we thought
        assert pytest.approx((enrc.elapsed, max_wait))
        # verify that the average time was what we expected
        assert pytest.approx((enrc.latency_avg, speed))
        assert enrc.latency_var < 1e-1

    def test_SLOW_concurrent_rpc(self, app, mock_ws, rpc):
        """verify multiple engines can run concurrently without interfering with each other"""
        chains = [app.config['POLYSWARMD'].chains[c] for c in ('home', 'side')]
        base_wait = 4
        gs = gevent.joinall([
            gevent.spawn(
                self.events,
                filters=[DumbFilter(speed=0.5)],
                ws=WebSocket(f'N{i + 1}'),
                # run them for different lengths of time to help verify isolation
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
        results = self.events(
            filters=[DumbFilter(speed=1) for _ in range(3)],
            ws=wrapper,
            RPC=rpc(chains),
            backoff=True
        )
        assert len(results) > 0


@pytest.fixture
def mock_ws(monkeypatch):

    def mock_send(self, msg_bytes):
        msg = ujson.loads(msg_bytes)
        assert isinstance(msg, object)
        self.queue.put_nowait(msg)

    monkeypatch.setattr(WebSocket, "send", mock_send)


@pytest.fixture(autouse=True)
def mock_fm(monkeypatch):
    monkeypatch.setattr(FilterManager, "setup_event_filters", lambda *_: True)


@pytest.fixture(scope='function', autouse=True)
def wrapper(mock_ws):
    return WebSocket('ws: N/A')


@pytest.fixture
def rpc(mock_fm):
    return EthereumRpc
