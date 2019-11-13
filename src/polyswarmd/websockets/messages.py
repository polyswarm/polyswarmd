import json
import uuid

from web3.utils import Event
from typing import List, Callable, Optional, TypeVar, Generic, Any

from types import MappingProxyType
from requests_futures.sessions import FuturesSession

from polyswarmd import app
from polyswarmd.bounties import substitute_metadata
from polyswarmd.artifacts.ipfs import IpfsServiceClient

from functools import lru_cache
from redis import redis


class WebsocketMessage(object):
    "Represent a message that can be handled by polyswarm-client"
    # This is the identifier used when building a websocket event identifier.
    _ws_event = 'websocket'
    __slots__ = ('data')

    @property
    def event(self):
        return self._ws_event

    def __init__(self, data={}):
        self.data = data

    def as_dict(self):
        "`as_dict' should return an object representing the websocket message that the client will consume"
        return {'event': self.event, 'data': self.data}

    def __str__(self):
        return json.dumps(self.as_dict())


class Connected(WebsocketMessage):
    _ws_event = 'connected'


class WebsocketEventlogMessage(WebsocketMessage):
    """Websocket message interface for etherem event entries. """

    __slots__ = ('event')
    _ws_fields = ()

    def __init__(self, event):
        self.event = MappingProxyType(event)
        if not self._ws_fields:
            raise ValueError("WebsocketEventlogMessage must define _ws_fields")

    def as_dict(self):
        return {
            'event': self.name,
            'data': self.format_data(),
            'block_number': self.block_number,
            'txhash': self.txhash
        }

    def format_data(self):
        "Format the event log entry for Websocket"
        for field in self._ws_fields:
            # This mode directly returns the key `field' from self.event
            # ('key_name')
            if isinstance(field, str):
                yield {field: self.event.args[field]}

            if isinstance(field, tuple) and len(field) == 2:
                key, arg = field
                yield {key: arg(self.event.args, key) if callable(arg) else arg}

            raise ValueError("Invalid _ws_fields")

    @property
    def block_number(self):
        return self.event.blockNumber

    @property
    def txhash(self):
        return self.event.transactionHash.hex()

    @property
    def event_name(self):
        "The event name used by web3 (e.g 'Transfer' or 'FeesUpdated')"
        return self.__class__.__name__


session = FuturesSession(adapter_kwargs={'max_retries': 3})


@lru_cache(15)
def fetch_metadata(uri: str,
                   validate=None,
                   session: FuturesSession = session,
                   artifact_client: IpfsServiceClient = app.config['POLYSWARMD'].artifact_client,
                   redis: redis = app.config['POLYSWARMD'].redis):
    return substitute_metadata(uri, artifact_client, session, validate, redis)


def as_uuid(e: Event, k: str) -> str:
    return str(uuid.UUID(int=e[k]))


def as_bv(e: Event, k: str) -> List[bool]:
    "Return the bitvector for a number, where 1 is 'True' and 0 is 'False'"
    return [True if b == '1' else False for b in format(e[k], f"0>{e.numArtifacts}b")]


bounty_guid = ('bounty_guid', lambda e: as_uuid(e, 'bountyGuid'))


class FeesUpdated(WebsocketEventlogMessage):
    _ws_event = 'fee_update'
    _ws_fields = ('bounty_fee',
                  'assertion_fee')


class WindowsUpdated(WebsocketEventlogMessage):
    _ws_event = 'window_update'
    _ws_fields = ('assertion_reveal_window',
                  'arbiter_vote_window')


def bids(e: Event) -> List[str]:
    return map(str, e.bids)

class NewAssertion(WebsocketEventlogMessage):
    _ws_event = 'assertion'
    _ws_fields = ('author',
                  ('mask', as_bv),
                  ('bid', bids),
                  'commitment',
                  'nonce',
                  ('verdicts', as_bv),
                  'metadata')


class NewVote(WebsocketEventlogMessage):
    _ws_event = 'vote'
    _ws_fields = (bounty_guid, ('votes', as_bv), 'voter')


class InitializedChannel(WebsocketEventlogMessage):
    _ws_event = 'initialized_channel'
    _ws_fields = (('guid', as_uuid),
                  'ambassador',
                  'expert',
                  ('multi_signature', 'msig'))


class LatestEvent(WebsocketEventlogMessage):
    _ws_event = 'block'
    event_name = 'latest'

    def as_dict(self):
        return {'event': self.name, 'data': {'number': self.block_number}}


class ClosedAgreement(WebsocketEventlogMessage):
    _ws_event = 'closed_agreement'
    _ws_fields = (('expert', '_expert'),
                  ('ambassador', '_ambassador'))


class StartedSettle(WebsocketEventlogMessage):
    _ws_event = 'settle_started'
    _ws_fields = ('initiator',
                  ('nonce', 'sequence'),
                  ('settle_period_end', 'settlementPeriodEnd'))


class SettleStateChallenged(WebsocketEventlogMessage):
    _ws_event = 'settle_challenged'
    _ws_fields = ('challenger',
                  ('nonce', 'sequence'),
                  ('settle_period_end', 'settlementPeriodEnd'))
