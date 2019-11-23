from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    Generic,
    Mapping,
    Optional,
    cast,
)
import ujson

from requests_futures.sessions import FuturesSession

from polyswarmartifact import ArtifactType
from polyswarmartifact.schema import Assertion as AssertionMetadata
from polyswarmartifact.schema import Bounty as BountyMetadata

from .json_schema import PSJSONSchema, SchemaDef
from .message_types import (
    ClosedAgreementMessageData,
    D,
    E,
    EventData,
    FeesUpdatedMessageData,
    InitializedChannelMessageData,
    LatestEventMessageData,
    NewAssertionMessageData,
    NewBountyMessageData,
    NewDepositMessageData,
    NewVoteMessageData,
    NewWithdrawalMessageData,
    QuorumReachedMessageData,
    RevealedAssertionMessageData,
    SettledBountyMessageData,
    SettleStateChallengedMessageData,
    StartedSettleMessageData,
    TransferMessageData,
    WebsocketEventMessage,
    WindowsUpdatedMessageData,
)


class WebsocketMessage(Generic[D]):
    "Represent a message that can be handled by polyswarm-client"
    # This is the identifier used when building a websocket event identifier.
    event: ClassVar[str]
    __slots__ = {'message': bytes}

    def __init__(self, data: Any = None):
        self.message = ujson.dumps(self.to_message(data)).encode('ascii')

    @classmethod
    def to_message(cls: Any, data: Any) -> WebsocketEventMessage[D]:
        return cast(WebsocketEventMessage, {'event': cls.event, 'data': data})

    def __bytes__(self):
        return self.message


class Connected(WebsocketMessage[str]):
    event: ClassVar[str] = 'connected'


class EventLogMessage(Generic[E]):
    "Extract `EventData` based on schema"

    schema: ClassVar[PSJSONSchema]
    contract_event_name: ClassVar[str]

    # The use of metaclasses complicates type-checking and inheritance, so to set a dynamic
    # class-property and type-checking annotations, we set it inside __init_subclass__.
    @classmethod
    def __init_subclass__(cls):
        super().__init_subclass__()
        cls.contract_event_name = cls.__name__

    @classmethod
    def extract(cls: Any, instance: Mapping) -> E:
        "Extract the fields indicated in schema from the event log message"
        return cls.schema.extract(instance)


# Commonly used schema properties
uint256: SchemaDef = {'type': 'integer'}
guid: SchemaDef = {'type': 'string', 'format': 'uuid'}
bounty_guid: SchemaDef = cast(SchemaDef, {**guid, 'srckey': 'bountyGuid'})
ethereum_address: SchemaDef = {'format': 'ethaddr', 'type': 'string'}


def int_to_bool_list(i):
    s = format(i, 'b')
    return [x == '1' for x in s[::-1]]


def safe_int_to_bool_list(num, max):
    if int(num) == 0:
        return [False] * int(max)
    else:
        converted = int_to_bool_list(num)
        return converted + [False] * (max - len(converted))


boolvector: SchemaDef = {
    'type': 'array',
    'items': 'boolean',
    'srckey': lambda k, e: safe_int_to_bool_list(e[k], e['numArtifacts'])
}

# partially applied `substitute_metadata' with AI, redis & session prefilled.
_substitute_metadata: Optional[Callable[[str, bool], Any]] = None


def fetch_metadata(msg: WebsocketEventMessage[D], validate=None,
                   override=None) -> WebsocketEventMessage[D]:
    """Fetch metadata with URI from `msg', validate it and merge the result

    >>> msg = {'event': 'test', 'data': { 'metadata': 'uri' }}
    >>> _substitute_metadata = lambda uri, validate: { 'hello': uri }
    >>> fetch_metadata(msg, override=_substitute_metadata)
    {'event': 'test', 'data': {'metadata': {'hello': 'uri'}}}
    """
    data = msg.get('data')
    if not data:
        return msg

    global _substitute_metadata
    if not _substitute_metadata:
        if override:
            _substitute_metadata = override
        else:
            from polyswarmd import app
            from polyswarmd.bounties import substitute_metadata
            config: Optional[Dict[str, Any]] = app.config
            ai = config['POLYSWARMD'].artifact_client
            session = FuturesSession(adapter_kwargs={'max_retries': 3})
            redis = config['POLYSWARMD'].redis

            def _substitute_metadata(uri: str, validate=None):
                return substitute_metadata(uri, ai, session, validate=validate, redis=redis)

    data.update(metadata=_substitute_metadata(data.get('metadata'), validate))
    return msg


class Transfer(EventLogMessage[TransferMessageData]):
    """Transfer

    >>> from pprint import pprint
    >>> args = {
    ... 'to': "0x00000000000000000000000000000001",
    ... 'from': "0x00000000000000000000000000000002",
    ... 'value': 1 }
    >>> pprint(Transfer.extract(args))
    {'from': '0x00000000000000000000000000000002',
     'to': '0x00000000000000000000000000000001',
     'value': '1'}
    """
    schema: ClassVar[PSJSONSchema] = PSJSONSchema({
        'properties': {
            'to': ethereum_address,
            'from': ethereum_address,
            'value': {
                'type': 'string'
            }
        }
    })


class NewDeposit(EventLogMessage[NewDepositMessageData]):
    """NewDeposit

    >>> args = {
    ... 'from': "0x00000000000000000000000000000002",
    ... 'value': 1 }
    >>> NewDeposit.extract(args)
    {'value': 1, 'from': '0x00000000000000000000000000000002'}
    """
    schema: ClassVar[PSJSONSchema] = PSJSONSchema({
        'properties': {
            'value': uint256,
            'from': ethereum_address,
        }
    })


class NewWithdrawal(EventLogMessage[NewWithdrawalMessageData]):
    """NewWithdrawal

    >>> args = {
    ... 'to': "0x00000000000000000000000000000001",
    ... 'from': "0x00000000000000000000000000000002",
    ... 'value': 1 }
    >>> NewWithdrawal.extract(args)
    {'to': '0x00000000000000000000000000000001', 'value': 1}
    """
    schema: ClassVar[PSJSONSchema] = PSJSONSchema({
        'properties': {
            'to': ethereum_address,
            'value': uint256,
        }
    })


class OpenedAgreement(EventLogMessage[Any]):

    @classmethod
    def extract(_cls, instance):
        return dict(instance)


class CanceledAgreement(EventLogMessage[Any]):

    @classmethod
    def extract(_cls, instance):
        return dict(instance)


class JoinedAgreement(EventLogMessage[Any]):

    @classmethod
    def extract(_cls, instance):
        return dict(instance)


class WebsocketFilterMessage(WebsocketMessage[D], EventLogMessage[D]):
    """Websocket message interface for etherem event entries. """
    event: ClassVar[str]
    schema: ClassVar[PSJSONSchema]
    contract_event_name: ClassVar[str]

    __slots__ = {'message': bytes}

    @classmethod
    def to_message(cls, event: EventData) -> WebsocketEventMessage[D]:
        return cast(
            WebsocketEventMessage[D], {
                'event': cls.event,
                'data': cls.extract(event['args']),
                'block_number': event['blockNumber'],
                'txhash': event['transactionHash'].hex()
            }
        )

    def __repr__(self):
        return f'<{self.contract_event_name} name={self.event}>'


class FeesUpdated(WebsocketFilterMessage[FeesUpdatedMessageData]):
    """FeesUpdated
    >>> args = {
    ... 'bountyFee': 5000000000000000,
    ... 'assertionFee': 5000000000000000 }
    >>> FeesUpdated.extract(args)
    {'bounty_fee': 5000000000000000, 'assertion_fee': 5000000000000000}
    """
    event: ClassVar[str] = 'fee_update'
    schema: ClassVar[PSJSONSchema] = PSJSONSchema({
        'properties': {
            'bounty_fee': {
                **uint256, 'srckey': 'bountyFee'
            },
            'assertion_fee': {
                **uint256, 'srckey': 'assertionFee'
            }
        },
    })


class WindowsUpdated(WebsocketFilterMessage[WindowsUpdatedMessageData]):
    """WindowsUpdated
    >>> args = {
    ... 'assertionRevealWindow': 100,
    ... 'arbiterVoteWindow': 105 }
    >>> WindowsUpdated.extract(args)
    {'assertion_reveal_window': 100, 'arbiter_vote_window': 105}
    """
    event: ClassVar[str] = 'window_update'
    schema: ClassVar[PSJSONSchema] = PSJSONSchema({
        'properties': {
            'assertion_reveal_window': {
                **uint256, 'srckey': 'assertionRevealWindow'
            },
            'arbiter_vote_window': {
                **uint256, 'srckey': 'arbiterVoteWindow'
            }
        }
    })


class NewBounty(WebsocketFilterMessage[NewBountyMessageData]):
    event: ClassVar[str] = 'bounty'
    schema: ClassVar[PSJSONSchema] = PSJSONSchema({
        'properties': {
            'guid': guid,
            'artifact_type': {
                'type': 'string',
                'enum': ['file', 'url'],
                'srckey': lambda k, e: ArtifactType.to_string(ArtifactType(e.artifactType))
            },
            'author': ethereum_address,
            'amount': {
                'type': 'string',
            },
            'uri': {
                'srckey': 'artifactURI'
            },
            'expiration': {
                'srckey': 'expirationBlock',
                'type': 'string',
            },
            'metadata': {
                'type': 'string'
            }
        }
    })

    @classmethod
    def to_message(cls, event) -> WebsocketEventMessage[NewBountyMessageData]:
        return fetch_metadata(super().to_message(event), validate=BountyMetadata.validate)


class NewAssertion(WebsocketFilterMessage[NewAssertionMessageData]):
    """NewAssertion
    >>> from pprint import pprint
    >>> args = {
    ... 'bountyGuid': 1,
    ... 'author': '0xF2E246BB76DF876Cef8b38ae84130F4F55De395b',
    ... 'index': 1,
    ... 'bid': [1,2,3],
    ... 'mask': 32,
    ... 'commitment': 100,
    ... 'numArtifacts': 4 }
    >>> event = {'args': args, 'blockNumber': 1, 'transactionHash': (11).to_bytes(16, byteorder='big')}
    >>> pprint(NewAssertion.to_message(event))
    {'block_number': 1,
     'data': {'author': '0xF2E246BB76DF876Cef8b38ae84130F4F55De395b',
              'bid': ['1', '2', '3'],
              'bounty_guid': '00000000-0000-0000-0000-000000000001',
              'commitment': '100',
              'index': 1,
              'mask': [False, False, False, False, False, True]},
     'event': 'assertion',
     'txhash': '0000000000000000000000000000000b'}
    """
    event: ClassVar[str] = 'assertion'
    schema: ClassVar[PSJSONSchema] = PSJSONSchema({
        'properties': {
            'bounty_guid': bounty_guid,
            'author': ethereum_address,
            'index': uint256,
            'bid': {
                'type': 'array',
                'items': 'string',
            },
            'mask': boolvector,
            'commitment': {
                'type': 'string',
            },
        },
    })


class RevealedAssertion(WebsocketFilterMessage[RevealedAssertionMessageData]):
    event: ClassVar[str] = 'reveal'
    schema: ClassVar[PSJSONSchema] = PSJSONSchema({
        'properties': {
            'bounty_guid': bounty_guid,
            'author': ethereum_address,
            'index': uint256,
            'nonce': {
                'type': 'string',
            },
            'verdicts': boolvector,
            'metadata': {}
        }
    })

    @classmethod
    def to_message(cls: Any,
                   event: EventData) -> WebsocketEventMessage[RevealedAssertionMessageData]:
        return fetch_metadata(super().to_message(event), validate=AssertionMetadata.validate)


class NewVote(WebsocketFilterMessage[NewVoteMessageData]):
    event: ClassVar[str] = 'vote'
    schema: ClassVar[PSJSONSchema] = PSJSONSchema({
        'properties': {
            'bounty_guid': bounty_guid,
            'voter': ethereum_address,
            'votes': boolvector
        }
    })


class QuorumReached(WebsocketFilterMessage[QuorumReachedMessageData]):
    event: ClassVar[str] = 'quorum'
    schema: ClassVar[PSJSONSchema] = PSJSONSchema({'properties': {'bounty_guid': bounty_guid}})


class SettledBounty(WebsocketFilterMessage[SettledBountyMessageData]):
    event: ClassVar[str] = 'settled_bounty'
    schema: ClassVar[PSJSONSchema] = PSJSONSchema({
        'properties': {
            'bounty_guid': bounty_guid,
            'settler': ethereum_address,
            'payout': uint256
        }
    })


class InitializedChannel(WebsocketFilterMessage[InitializedChannelMessageData]):
    event: ClassVar[str] = 'initialized_channel'
    schema: ClassVar[PSJSONSchema] = PSJSONSchema({
        'properties': {
            'ambassador': ethereum_address,
            'expert': ethereum_address,
            'guid': guid,
            'multi_signature': {
                **ethereum_address,
                'srckey': 'msig',
            }
        }
    })


class ClosedAgreement(WebsocketFilterMessage[ClosedAgreementMessageData]):
    event: ClassVar[str] = 'closed_agreement'
    schema: ClassVar[PSJSONSchema] = PSJSONSchema({
        'properties': {
            'ambassador': {
                **ethereum_address, 'srckey': '_ambassador'
            },
            'expert': {
                'srckey': '_expert',
                **ethereum_address
            }
        }
    })


class StartedSettle(WebsocketFilterMessage[StartedSettleMessageData]):
    event: ClassVar[str] = 'settle_started'
    schema: ClassVar[PSJSONSchema] = PSJSONSchema({
        'properties': {
            'initiator': ethereum_address,
            'nonce': {
                'srckey': 'sequence',
                **uint256
            },
            'settle_period_end': {
                'srckey': 'settlementPeriodEnd',
                **uint256
            }
        }
    })


class SettleStateChallenged(WebsocketFilterMessage[SettleStateChallengedMessageData]):
    event: ClassVar[str] = 'settle_challenged'
    schema: ClassVar[PSJSONSchema] = PSJSONSchema({
        'properties': {
            'challenger': ethereum_address,
            'nonce': {
                'srckey': 'sequence',
                **uint256
            },
            'settle_period_end': {
                'srckey': 'settlementPeriodEnd',
                **uint256
            }
        }
    })


class Deprecated(WebsocketFilterMessage[None]):
    event: ClassVar[str] = 'deprecated'

    def __bytes__(self):
        return b'{}'


class LatestEvent(WebsocketFilterMessage[LatestEventMessageData]):
    event: ClassVar[str] = 'block'
    contract_event_name: ClassVar[str] = 'latest'
    _chain: ClassVar[Any]

    @classmethod
    def to_message(cls, event):
        return {'event': cls.event, 'data': {'number': cls._chain.blockNumber}}

    @classmethod
    def make(cls, chain):
        cls._chain = chain
        return cls
