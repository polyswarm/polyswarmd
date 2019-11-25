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
        cls.contract_event_name = cls.__name__
        super().__init_subclass__()

    @classmethod
    def extract(cls: Any, instance: Mapping) -> E:
        "Extract the fields indicated in schema from the event log message"
        return cls.schema.extract(instance)


# Commonly used schema properties
uint256: SchemaDef = {'type': 'integer'}
guid: SchemaDef = {'type': 'string', 'format': 'uuid'}
bounty_guid: SchemaDef = cast(SchemaDef, {**guid, 'srckey': 'bountyGuid'})
ethereum_address: SchemaDef = {'format': 'ethaddr', 'type': 'string'}


def _int_to_bool_list(i):
    s = format(i, 'b')
    return [x == '1' for x in s[::-1]]


def safe_int_to_bool_list(num, max):
    if int(num) == 0:
        return [False] * int(max)
    else:
        converted = _int_to_bool_list(num)
        return converted + [False] * (max - len(converted))


def _get_boolvector(k: str, e: EventData):
    """Safely Convert in to "bool list"

    >>> _get_boolvector('test', {'test': 128, 'numArtifacts': 9})
    [False, False, False, False, False, False, False, True, False]
    >>> _get_boolvector('test', {'test': 15, 'numArtifacts': 4})
    [True, True, True, True]
    >>> _get_boolvector('test', {'test': 127, 'numArtifacts': 8})
    [True, True, True, True, True, True, True, False]
    """
    return safe_int_to_bool_list(e[k], e['numArtifacts'])


boolvector: SchemaDef = {'type': 'array', 'items': 'boolean', 'srckey': _get_boolvector}

# partially applied `substitute_metadata' with AI, redis & session prefilled.
_substitute_metadata: Optional[Callable[[str, bool], Any]] = None


def fetch_metadata(msg: WebsocketEventMessage[D], validate=None,
                   override=None) -> WebsocketEventMessage[D]:
    """Fetch metadata with URI from `msg', validate it and merge the result

    doctest:
    When the doctest runs, _substitute_metadata is already defined outside the doctest. This won't
    trigger network IO

    >>> msg = {'event': 'test', 'data': { 'metadata': 'uri' }}
    >>> pprint(fetch_metadata(msg))
    {'data': {'metadata': {'malware_family': 'EICAR',
                           'scanner': {'environment': {'architecture': 'x86_64',
                                                       'operating_system': 'Linux'}}}},
     'event': 'test'}
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

    doctest:

    >>> pprint(Transfer.extract({'to': addr1, 'from': addr2, 'value': 1 }))
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

    doctest:

    >>> NewDeposit.extract({'from': addr2, 'value': 1 })
    {'value': 1, 'from': '0x00000000000000000000000000000002'}
    >>> NewDeposit.contract_event_name
    'NewDeposit'
    """
    schema: ClassVar[PSJSONSchema] = PSJSONSchema({
        'properties': {
            'value': uint256,
            'from': ethereum_address,
        }
    })


class NewWithdrawal(EventLogMessage[NewWithdrawalMessageData]):
    """NewWithdrawal

    doctest:

    >>> args = {
    ... 'to': "0x00000000000000000000000000000001",
    ... 'from': "0x00000000000000000000000000000002",
    ... 'value': 1 }
    >>> NewWithdrawal.extract(args)
    {'to': '0x00000000000000000000000000000001', 'value': 1}
    >>> NewWithdrawal.contract_event_name
    'NewWithdrawal'
    """
    schema: ClassVar[PSJSONSchema] = PSJSONSchema({
        'properties': {
            'to': ethereum_address,
            'value': uint256,
        }
    })


class OpenedAgreement(EventLogMessage[Dict]):
    """OpenedAgreement

    doctest:

    >>> OpenedAgreement.extract({ 'to': addr1, 'from': addr2, 'value': 1 })
    {'to': '0x00000000000000000000000000000001', 'from': '0x00000000000000000000000000000002', 'value': 1}
    >>> OpenedAgreement.contract_event_name
    'OpenedAgreement'
    """

    @classmethod
    def extract(_cls, instance):
        return dict(instance)


class CanceledAgreement(EventLogMessage[Dict]):

    @classmethod
    def extract(_cls, instance):
        return dict(instance)


class JoinedAgreement(EventLogMessage[Dict]):

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
                'data': cls.extract(event.args),
                'block_number': event['blockNumber'],
                'txhash': event['transactionHash'].hex()
            }
        )

    def __repr__(self):
        return f'<{self.contract_event_name} name={self.event}>'


class FeesUpdated(WebsocketFilterMessage[FeesUpdatedMessageData]):
    """FeesUpdated

    doctest:

    >>> event = mkevent({'bountyFee': 5000000000000000, 'assertionFee': 5000000000000000 })
    >>> decoded_msg(FeesUpdated(event))
    {'block_number': 117,
     'data': {'assertion_fee': 5000000000000000, 'bounty_fee': 5000000000000000},
     'event': 'fee_update',
     'txhash': '0000000000000000000000000000000b'}
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

    doctest:

    >>> event = mkevent({
    ... 'assertionRevealWindow': 100,
    ... 'arbiterVoteWindow': 105 })
    >>> decoded_msg(WindowsUpdated(event))
    {'block_number': 117,
     'data': {'arbiter_vote_window': 105, 'assertion_reveal_window': 100},
     'event': 'window_update',
     'txhash': '0000000000000000000000000000000b'}
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

    doctest:

    >>> event = mkevent({
    ... 'bountyGuid': 1,
    ... 'author': '0xF2E246BB76DF876Cef8b38ae84130F4F55De395b',
    ... 'index': 1,
    ... 'bid': [1,2,3],
    ... 'mask': 32,
    ... 'commitment': 100,
    ... 'numArtifacts': 4 })
    >>> decoded_msg(NewAssertion(event))
    {'block_number': 117,
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
    """RevealedAssertion

    doctest:
    When the doctest runs, _substitute_metadata is already defined outside the doctest. This won't
    trigger network IO

    >>> event = mkevent({
    ... 'bountyGuid': 2,
    ... 'author': '0xDF9246BB76DF876Cef8bf8af8493074755feb58c',
    ... 'index': 10,
    ... 'verdicts': 128,
    ... 'nonce': 8,
    ... 'numArtifacts': 4,
    ... 'metadata': 'EICAR',})
    >>> decoded_msg(RevealedAssertion(event))
    {'block_number': 117,
     'data': {'author': '0xDF9246BB76DF876Cef8bf8af8493074755feb58c',
              'bounty_guid': '00000000-0000-0000-0000-000000000002',
              'index': 10,
              'metadata': {'malware_family': 'EICAR',
                           'scanner': {'environment': {'architecture': 'x86_64',
                                                       'operating_system': 'Linux'}}},
              'nonce': '8',
              'verdicts': [False, False, False, False, False, False, False, True]},
     'event': 'reveal',
     'txhash': '0000000000000000000000000000000b'}
    """
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
    """NewVote

    doctest:

    >>> event = mkevent({
    ... 'bountyGuid': 2,
    ... 'voter': '0xDF9246BB76DF876Cef8bf8af8493074755feb58c',
    ... 'votes': 128,
    ... 'numArtifacts': 4 })
    >>> new_vote = NewVote(event)
    >>> new_vote.contract_event_name
    'NewVote'
    >>> decoded_msg(new_vote)
    {'block_number': 117,
     'data': {'bounty_guid': '00000000-0000-0000-0000-000000000002',
              'voter': '0xDF9246BB76DF876Cef8bf8af8493074755feb58c',
              'votes': [False, False, False, False, False, False, False, True]},
     'event': 'vote',
     'txhash': '0000000000000000000000000000000b'}
    """
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
    """InitializedChannel

    >>> event = mkevent({
    ... 'ambassador': '0xF2E246BB76DF876Cef8b38ae84130F4F55De395b',
    ... 'expert': '0xDF9246BB76DF876Cef8bf8af8493074755feb58c',
    ... 'guid': 1,
    ... 'msig': '0x789246BB76D18C6C7f8bd8ac8423478795f71bf9' })
    >>> msg = InitializedChannel(event)
    >>> msg.contract_event_name
    'InitializedChannel'
    >>> decoded_msg(msg)
    {'block_number': 117,
     'data': {'ambassador': '0xF2E246BB76DF876Cef8b38ae84130F4F55De395b',
              'expert': '0xDF9246BB76DF876Cef8bf8af8493074755feb58c',
              'guid': '00000000-0000-0000-0000-000000000001',
              'multi_signature': '0x789246BB76D18C6C7f8bd8ac8423478795f71bf9'},
     'event': 'initialized_channel',
     'txhash': '0000000000000000000000000000000b'}
    """
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
    """ClosedAgreement

    doctest:

    >>> event = mkevent({
    ... '_ambassador': '0xF2E246BB76DF876Cef8b38ae84130F4F55De395b',
    ... '_expert': '0xDF9246BB76DF876Cef8bf8af8493074755feb58c', })
    >>> pprint(ClosedAgreement.to_message(event))
    {'block_number': 117,
     'data': {'ambassador': '0xF2E246BB76DF876Cef8b38ae84130F4F55De395b',
              'expert': '0xDF9246BB76DF876Cef8bf8af8493074755feb58c'},
     'event': 'closed_agreement',
     'txhash': '0000000000000000000000000000000b'}
    """
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
    """Deprecated

    doctest:

    >>> LatestEvent.make(chain1)
    <class 'websockets.messages.LatestEvent'>
    >>> event = mkevent({'a': 1, 'hello': 'world', 'should_not_be_here': True})
    >>> msg = Deprecated(event)
    >>> msg.contract_event_name
    'Deprecated'
    >>> decoded_msg(msg)
    {'block_number': 117,
     'data': {},
     'event': 'deprecated',
     'txhash': '0000000000000000000000000000000b'}
    """
    event: ClassVar[str] = 'deprecated'

    @classmethod
    def to_message(cls, event: EventData) -> WebsocketEventMessage[D]:
        return cast(
            WebsocketEventMessage[D], {
                'event': 'deprecated',
                'data': {},
                'block_number': event['blockNumber'],
                'txhash': event['transactionHash'].hex()
            }
        )


class LatestEvent(WebsocketFilterMessage[LatestEventMessageData]):
    """LatestEvent

    doctest:

    >>> LatestEvent.make(chain1)
    <class 'websockets.messages.LatestEvent'>
    >>> event = mkevent({'a': 1, 'hello': 'world', 'should_not_be_here': True})
    >>> msg = LatestEvent(event)
    >>> msg.contract_event_name
    'latest'
    >>> decoded_msg(msg)
    {'data': {'number': 117}, 'event': 'block'}
    """
    event: ClassVar[str] = 'block'
    _chain: ClassVar[Any]

    @classmethod
    def to_message(cls, event):
        return {'event': cls.event, 'data': {'number': cls._chain.blockNumber}}

    @classmethod
    def make(cls, chain):
        cls.contract_event_name = 'latest'
        cls._chain = chain
        return cls
