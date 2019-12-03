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
    DeprecatedData,
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

    @classmethod
    def serialize_message(cls: Any, data: Any) -> bytes:
        return ujson.dumps(cls.to_message(data)).encode('ascii')

    @classmethod
    def to_message(cls: Any, data: Any) -> WebsocketEventMessage[D]:
        return cast(WebsocketEventMessage, {'event': cls.event, 'data': data})


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


class MetadataHandler:
    """Handles calling polyswarmd.bounties.substitute_metadata, only available at runtime

    doctest:
    When the doctest runs, MetadataHandler._substitute_metadata is already defined outside this
    doctest (in __main__.py). Running this as a doctest will not trigger network IO.

    >>> msg = {'event': 'test', 'data': { 'metadata': 'uri' }}
    >>> MetadataHandler.fetch(msg, validate=None)
    {'event': 'test', 'data': {'metadata': 'uri'}}
    """
    # partially applied `substitute_metadata' with AI, redis & session prefilled.
    _substitute_metadata: ClassVar[Optional[Callable[[str, bool], Any]]] = None

    @classmethod
    def initialize(cls):
        """Create & assign a new implementation of _substitute_metadata"""
        from polyswarmd import app
        from polyswarmd.bounties import substitute_metadata
        config: Optional[Dict[str, Any]] = app.config
        ai = config['POLYSWARMD'].artifact_client
        session = FuturesSession(adapter_kwargs={'max_retries': 3})
        redis = config['POLYSWARMD'].redis

        def _substitute_metadata_impl(uri: str, validate=None):
            return substitute_metadata(uri, ai, session, validate=validate, redis=redis)

        cls._substitute_metadata = _substitute_metadata_impl

    @classmethod
    def fetch(cls, msg: WebsocketEventMessage[D],
              validate=AssertionMetadata.validate) -> WebsocketEventMessage[D]:
        """Fetch metadata with URI from `msg', validate it and merge the result"""
        data = msg.get('data')
        if not data:
            return msg

        data.update(metadata=cls.substitute_metadata(data.get('metadata'), validate))
        return msg

    @classmethod
    def substitute_metadata(cls, uri: str, validate):
        "Handles the actual call to `_substitute_metadata`"
        if not cls._substitute_metadata:
            cls.initialize()
        return cls._substitute_metadata(uri, validate)


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

    >>> NewWithdrawal.extract({'to': addr1, 'from': addr2, 'value': 1 })
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
    >>> decoded_msg(FeesUpdated.serialize_message(event))
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
    >>> decoded_msg(WindowsUpdated.serialize_message(event))
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
    """NewBounty

    doctest:
    When the doctest runs, MetadataHandler._substitute_metadata is already defined outside this
    doctest (in __main__.py). Running this as a doctest will not trigger network IO.

    >>> event = mkevent({
    ... 'guid': 1066,
    ... 'artifactType': 1,
    ... 'author': addr1,
    ... 'amount': 10,
    ... 'artifactURI': '912bnadf01295',
    ... 'expirationBlock': 118,
    ... 'metadata': 'ZWassertionuri'})
    >>> decoded_msg(NewBounty.serialize_message(event))
    {'block_number': 117,
     'data': {'amount': '10',
              'artifact_type': 'url',
              'author': '0x00000000000000000000000000000001',
              'expiration': '118',
              'guid': '00000000-0000-0000-0000-00000000042a',
              'metadata': [{'bounty_id': 69540800813340,
                            'extended_type': 'EICAR virus test files',
                            'filename': 'eicar_true',
                            'md5': '44d88612fea8a8f36de82e1278abb02f',
                            'mimetype': 'text/plain',
                            'sha1': '3395856ce81f2b7382dee72602f798b642f14140',
                            'sha256': '275a021bbfb6489e54d471899f7db9d1663fc695ec2fe2a2c4538aabf651fd0f',
                            'size': 68,
                            'type': 'FILE'}],
              'uri': '912bnadf01295'},
     'event': 'bounty',
     'txhash': '0000000000000000000000000000000b'}
    """
    event: ClassVar[str] = 'bounty'
    schema: ClassVar[PSJSONSchema] = PSJSONSchema({
        'properties': {
            'guid': guid,
            'artifact_type': {
                'type': 'string',
                'enum': [name.lower() for name, value in ArtifactType.__members__.items()],
                'srckey': lambda k, e: ArtifactType.to_string(ArtifactType(e['artifactType']))
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
        return MetadataHandler.fetch(super().to_message(event), validate=BountyMetadata.validate)


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
    >>> decoded_msg(NewAssertion.serialize_message(event))
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
    When the doctest runs, MetadataHandler._substitute_metadata is already defined outside this
    doctest (in __main__.py). Running this as a doctest will not trigger network IO.


    >>> event = mkevent({
    ... 'bountyGuid': 2,
    ... 'author': '0xDF9246BB76DF876Cef8bf8af8493074755feb58c',
    ... 'index': 10,
    ... 'verdicts': 128,
    ... 'nonce': 8,
    ... 'numArtifacts': 4,
    ... 'metadata': 'ZWbountyuri' })
    >>> decoded_msg(RevealedAssertion.serialize_message(event))
    {'block_number': 117,
     'data': {'author': '0xDF9246BB76DF876Cef8bf8af8493074755feb58c',
              'bounty_guid': '00000000-0000-0000-0000-000000000002',
              'index': 10,
              'metadata': [{'malware_family': 'EICAR',
                            'scanner': {'environment': {'architecture': 'x86_64',
                                                        'operating_system': 'Linux'}}}],
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
        return MetadataHandler.fetch(super().to_message(event), validate=AssertionMetadata.validate)


class NewVote(WebsocketFilterMessage[NewVoteMessageData]):
    """NewVote

    doctest:

    >>> event = mkevent({
    ... 'bountyGuid': 2,
    ... 'voter': '0xDF9246BB76DF876Cef8bf8af8493074755feb58c',
    ... 'votes': 128,
    ... 'numArtifacts': 4 })
    >>> decoded_msg(NewVote.serialize_message(event))
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
    """QuorumReached

    doctest:

    >>> event = mkevent({'bountyGuid': 16577})
    >>> decoded_msg(QuorumReached.serialize_message(event))
    {'block_number': 117,
     'data': {'bounty_guid': '00000000-0000-0000-0000-0000000040c1'},
     'event': 'quorum',
     'txhash': '0000000000000000000000000000000b'}
    """
    event: ClassVar[str] = 'quorum'
    schema: ClassVar[PSJSONSchema] = PSJSONSchema({'properties': {'bounty_guid': bounty_guid}})


class SettledBounty(WebsocketFilterMessage[SettledBountyMessageData]):
    """SettledBounty

    doctest:

    >>> event = mkevent({
    ... 'bountyGuid': 16577,
    ... 'settler': addr1,
    ... 'payout': 1000 })
    >>> decoded_msg(SettledBounty.serialize_message(event))
    {'block_number': 117,
     'data': {'bounty_guid': '00000000-0000-0000-0000-0000000040c1',
              'payout': 1000,
              'settler': '0x00000000000000000000000000000001'},
     'event': 'settled_bounty',
     'txhash': '0000000000000000000000000000000b'}

    """
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
    >>> decoded_msg(InitializedChannel.serialize_message(event))
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
    >>> decoded_msg(ClosedAgreement.serialize_message(event))
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
    """StartedSettle

    doctest:

    >>> event = mkevent({
    ... 'initiator': addr1,
    ... 'sequence': 1688,
    ... 'settlementPeriodEnd': 229 })
    >>> decoded_msg(StartedSettle.serialize_message(event))
    {'block_number': 117,
     'data': {'initiator': '0x00000000000000000000000000000001',
              'nonce': 1688,
              'settle_period_end': 229},
     'event': 'settle_started',
     'txhash': '0000000000000000000000000000000b'}

    """
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
    """SettleStateChallenged

    doctest:

    >>> event = mkevent({
    ... 'challenger': addr1,
    ... 'sequence': 1688,
    ... 'settlementPeriodEnd': 229 })
    >>> decoded_msg(SettleStateChallenged.serialize_message(event))
    {'block_number': 117,
     'data': {'challenger': '0x00000000000000000000000000000001',
              'nonce': 1688,
              'settle_period_end': 229},
     'event': 'settle_challenged',
     'txhash': '0000000000000000000000000000000b'}
    """
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


class Deprecated(WebsocketFilterMessage[DeprecatedData]):
    """Deprecated

    doctest:

    >>> event = mkevent({'rollover': True})
    >>> Deprecated.contract_event_name
    'Deprecated'
    >>> decoded_msg(Deprecated.serialize_message(event))
    {'block_number': 117,
     'data': {'rollover': false},
     'event': 'deprecated',
     'txhash': '0000000000000000000000000000000b'}
    """
    event: ClassVar[str] = 'deprecated'
    schema: ClassVar[PSJSONSchema] = PSJSONSchema({
        'properties': {
            'rollover': {
                'type': 'boolean'
            },
        }
    })


class Undeprecated(WebsocketFilterMessage[None]):
    """Deprecated

    doctest:

    >>> event = mkevent({'a': 1, 'hello': 'world', 'should_not_be_here': True})
    >>> Undeprecated.contract_event_name
    'Undeprecated'
    >>> decoded_msg(Undeprecated.serialize_message(event))
    {'block_number': 117,
     'data': {},
     'event': 'undeprecated',
     'txhash': '0000000000000000000000000000000b'}
    """
    event: ClassVar[str] = 'undeprecated'

    @classmethod
    def to_message(cls, event: EventData) -> WebsocketEventMessage[D]:
        return cast(
            WebsocketEventMessage[D], {
                'event': 'undeprecated',
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
    >>> LatestEvent.contract_event_name
    'latest'
    >>> decoded_msg(LatestEvent.serialize_message(event))
    {'data': {'number': 117}, 'event': 'block'}
    """
    event: ClassVar[str] = 'block'
    contract_event_name: ClassVar[str] = 'latest'
    _chain: ClassVar[Any]

    @classmethod
    def to_message(cls, event):
        return {'event': cls.event, 'data': {'number': cls._chain.blockNumber}}

    @classmethod
    def make(cls, chain):
        cls.contract_event_name = 'latest'
        cls._chain = chain
        return cls
