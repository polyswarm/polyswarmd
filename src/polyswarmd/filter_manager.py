import uuid

from web3.utils import Filter, Event
from typing import Optional

from types import MappingProxyType
from requests_futures.sessions import FuturesSession

from polyswarmd import app
from polyswarmd.bounties import substitute_metadata
from polyswarmd.websockets import WebsocketMessage
from polyswarmd.artifacts.ipfs import IpfsServiceClient

from functools import lru_cache
from redis import redis

session = FuturesSession(adapter_kwargs={'max_retries': 3})

@lru_cache(15)
def fetch_metadata(uri: str,
                   validate=None,
                   session: FuturesSession = session,
                   artifact_client: IpfsServiceClient = app.config['POLYSWARMD'].artifact_client,
                   redis: redis = app.config['POLYSWARMD'].redis):
    return substitute_metadata(uri, artifact_client, session, validate, redis)


def as_uuid(e: Event, k: str):
    return str(uuid.UUID(int=e[k]))


def as_bv(e: Event, k: str):
    "Return the bitvector for a number, where 1 is 'True' and 0 is 'False'"
    return [True if b == '1' else False for b in format(e[k], f"0>{e.numArtifacts}b")]


bounty_guid = ('bounty_guid', lambda e, _: as_uuid(e, 'bountyGuid'))

class EventEntryWebsocketMessage(WebsocketMessage):
    """Websocket message interface for etherem event entries. """

    __slots__ = ('event')
    _ws_fields = ()

    def __init__(self, event):
        self.event = MappingProxyType(event)
        if not self._ws_fields:
            raise ValueError("EventEntryWebsocketMessage must define _ws_fields")

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
    def filter_id(self):
        "The event name used by web3 (e.g 'Transfer' or 'FeesUpdated')"
        return self.__class__.__name__


class FeesUpdated(EventEntryWebsocketMessage):
    _ws_event = 'fee_update'
    _ws_fields = ('bounty_fee', 'assertion_fee')


class WindowsUpdated(EventEntryWebsocketMessage):
    _ws_event = 'window_update'
    _ws_fields = ('assertion_reveal_window', 'arbiter_vote_window')


class NewAssertion(EventEntryWebsocketMessage):
    _ws_event = 'assertion'
    _ws_fields = ('author', ('mask', as_bv), ('bid', lambda e: map(str, e.bids)), 'commitment', 'nonce',
                       ('verdicts', as_bv), 'metadata')


class NewVote(EventEntryWebsocketMessage):
    _ws_event = 'vote'
    _ws_fields = (bounty_guid, ('votes', as_bv), 'voter')


class QuorumReached(EventEntryWebsocketMessage):
    _ws_event = 'quorum'
    _ws_fields = (bounty_guid)


class SettledBounty(EventEntryWebsocketMessage):
    _ws_event = 'settled_bounty'
    _ws_fields = (bounty_guid, 'settler', 'payout')


class Deprecated(EventEntryWebsocketMessage):
    _ws_event = 'deprecated'
    _ws_fields = ()


class NewBounty(EventEntryWebsocketMessage):
    _ws_event = 'bounty'
    _ws_fields = (('guid', as_uuid), 'artifact_type', 'author', 'amount', ('uri', 'artifactURI'),
                       ('expiration', 'expirationBlock'), ('metadata', fetch_metadata))


class RevealedAssertion(EventEntryWebsocketMessage):
    _ws_event = 'reveal'
    _ws_fields = (bounty_guid, 'author', 'index', 'nonce', ('verdicts', as_bv), ('metadata', fetch_metadata))


class InitializedChannel(EventEntryWebsocketMessage):
    _ws_event = 'initialized_channel'
    _ws_fields = (('guid', as_uuid), 'ambassador', 'expert', ('multi_signature', 'msig'))


class LatestEvent(EventEntryWebsocketMessage):
    _ws_event = 'block'
    filter_id = 'latest'

    def as_dict(self):
        return {'event': self.name, 'data': {'number': self.block_number}}


class ClosedAgreement(EventEntryWebsocketMessage):
    _ws_event = 'closed_agreement'
    _ws_fields = (('expert', '_expert'), ('ambassador', '_ambassador'))

class StartedSettle(EventEntryWebsocketMessage):
    _ws_event = 'settle_started'
    _ws_fields = ('initiator', ('nonce', 'sequence'), ('settle_period_end', 'settlementPeriodEnd'))

class SettleStateChallenged(EventEntryWebsocketMessage):
    _ws_event = 'settle_challenged'
    _ws_fields = ('challenger', ('nonce', 'sequence'), ('settle_period_end', 'settlementPeriodEnd'))


class FilterManager(object):
    """Manages access to filtered Ethereum events.

    TODO: Bundle `register' calls together to reduce ethereum-filter-checking waste.
    """
    def __init__(self):
        self.filters = []

    def register(self, flt: Filter, ws_serializer: Optional[EventEntryWebsocketMessage]):
        "Add a new filter, with an optional associated WebsocketMessage-serializer class"
        self.filters.append((flt, ws_serializer))

    def unregister_all(self):
        self.filters = []

    def has_registered(self):
        return len(self.filters) > 0

    def flush(self):
        for filt, _ in self.filters:
            yield from filt.get_new_entries()

    def new_ws_events(self):
        "Yields all of the new entries matches by the filters (in-order), returning each as a websocket message."
        for filt, cls in self.filters:
            for event in filt.get_new_entries():
                yield cls(event)
