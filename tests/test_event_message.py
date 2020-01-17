from collections.abc import Collection
from contextlib import contextmanager
from math import ceil
import pprint
import statistics
import time
from typing import Any, ClassVar, List, Mapping, Optional
import uuid

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


class DumbFilter:
    def __init__(self, speed=1.0, prev=0, extra={}, start=None, backoff=True, ident=None, source=None):
        self.speed = speed
        self.prev = prev
        self.extra = extra
        self.start = start
        self.backoff = backoff
        self.ident = ident
        self.source = source

    # Verify that _something_ is being passed in, even if we're not using it.
    def __call__(self, contract_event_name):
        return self

    def to_msg(self, idx):
        # XXX: do not use id(self) here, the lifetime of each dumbfilter does not overlap
        if not self.ident:
            self.ident = str(uuid.uuid4())
        return {
            FILTERID: self.ident,
            NTH: idx,
            TX_TS: now(),
            'speed': self.speed,
            START: self.start,
            BACKOFF: self.backoff
        }

    def get_new_entries(self):
        if not self.start:
            self.start = now()
        prev = self.prev
        curr = ceil(elapsed(self.start) / self.speed)
        yield from map(self.to_msg, range(prev, curr))
        self.prev = curr


class enrich(Collection):
    msgs: List[Mapping]

    elapsed = property(lambda msgs: max(msgs[TX_TS]) - min(msgs[TX_TS]))
    bundles = property(lambda msgs: [v for v in msgs[TXDIFF] if v > 1e-1])
    responses = property(lambda msgs: len(msgs.bundles))
    latency_var = property(lambda msgs: statistics.pvariance(msgs.bundles))
    latency_avg = property(lambda msgs: statistics.mean(msgs.bundles))
    usertime_avg = property(lambda msgs: statistics.mean(msgs[CPUTIME]))
    sources = property(lambda msgs: len(set(msgs[FILTERID])))

    def __init__(self, messages, extra={}):
        self.msgs = []
        prev = {}
        for msg in messages:
            data = msg.get('data', {})
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

    def __getitem__(self, key):
        return [msg[key] for msg in self.msgs]

    def __str__(self):
        props = ['elapsed', 'responses', 'latency_var', 'latency_avg', 'usertime_avg']
        return '<%s summary=%s>' % (type(self), {k: getattr(self, k) for k in props})


class TestWebsockets:

    @contextmanager
    def start_rpc(self, filters, ws, RPC):
        RPC.register(ws)
        for ft in filters:
            RPC.filter_manager.register(ft, NOPMessage, backoff=ft.backoff)
        yield RPC
        RPC.unregister(ws)
        assert len(RPC.websockets) == 0

    def events(self, filters, ws, RPC, max_wait=3, timeout=1):
        """Mimic the behavior of /events endpoint for tests"""

        # NOTE: KEEP IMPL CLOSE TO `event_message.py#init_websockets#events(ws)`
        # I wasn't able to find how to use a Flask app client with `Sockets` without
        # making some changes to how `init_websockets` works, so this function
        # just reproduces that behavior in this testable environment, please let
        # met know if you've figured out a way around this -zv
        start = now()

        with self.start_rpc(filters=filters, ws=ws, RPC=RPC):
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
    def test_SLOW_recv(self, chains, mock_ws, rpc):
        """Verify that we can recieve msgs with uniform timing"""
        max_wait = 3
        speed = 0.5
        sources = 10
        filters = [DumbFilter(speed=speed) for _ in range(sources)]
        count = int(sum(max_wait // f.speed for f in filters))
        enrc = self.events(filters=filters, ws=mock_ws('NA'), max_wait=max_wait, RPC=rpc(chains))
        # just to be sure
        assert len(enrc) > 0
        # the number of msgs should be ~ (elapsed_time / msg_rate) * num_of_msg_srcs)
        assert abs(len(enrc) - count) <= 1
        assert enrc.sources == sources
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
                filters=[DumbFilter(speed=0.5), DumbFilter(speed=0.5)],
                ws=mock_ws(f'N{i + 1}'),
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
    def test_SLOW_backoff(self, chains, rpc, mock_ws):
        """verify backoff works"""
        max_wait = 4
        speed = 0.5
        filters = [
            DumbFilter(speed=speed, backoff=True),
            DumbFilter(speed=speed, backoff=False),
            DumbFilter(speed=speed, backoff=True),
            DumbFilter(speed=speed, backoff=False),
            DumbFilter(speed=speed, backoff=True),
        ]
        enrc = self.events(
            filters=filters,
            ws=mock_ws('NA'),
            max_wait=max_wait,
            RPC=rpc(chains),
        )
        # just to be sure
        assert len(enrc) > 0
        assert enrc.sources == len(filters)
        # verify the time elapsed took what we thought
        assert pytest.approx((enrc.elapsed, max_wait))
        # verify that the average time was what we expected
        assert enrc.latency_var < 1e-1
        # verify that the average time was what we expected
        assert pytest.approx((enrc.latency_avg, speed))


@pytest.fixture
def mock_ws(monkeypatch):

    def mock_send(self, msg_bytes):
        msg = ujson.loads(msg_bytes)
        assert isinstance(msg, object)
        self.queue.put_nowait(msg)

    monkeypatch.setattr(WebSocket, "send", mock_send)
    return WebSocket


@pytest.fixture
def mock_fm(monkeypatch):
    monkeypatch.setattr(FilterManager, "setup_event_filters", lambda s, *_: s.flush())


@pytest.fixture
def rpc(mock_fm):
    return EthereumRpc
