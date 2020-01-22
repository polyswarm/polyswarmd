import abc
from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    Generic,
    List,
    Mapping,
    Optional,
    Type,
    TypeVar,
    cast,
)
import uuid

from pydantic import BaseModel, Field, constr
from requests_futures.sessions import FuturesSession
import ujson

from polyswarmartifact import ArtifactType as _ArtifactType
from polyswarmartifact.schema import Assertion as AssertionMetadata
from polyswarmartifact.schema import Bounty as BountyMetadata
from polyswarmd.utils import safe_int_to_bool_list


class EventData(Mapping):
    """Event data returned from web3 filter requests"""
    args: Dict[str, Any]
    event: str
    logIndex: int
    transactionIndex: int
    transactionHash: bytes
    address: str
    blockHash: bytes
    blockNumber: int


class WebsocketMessage(BaseModel):
    "Represent a message that can be handled by polyswarm-client"
    @classmethod
    def serialize_message(cls: Any, data: Any) -> bytes:
        return ujson.dumps(cls.to_message(data)).encode('ascii')

    @classmethod
    def to_message(cls: Any, data: Any):
        raise NotImplementedError


class Connected(WebsocketMessage):
    event_id: ClassVar[str] = 'connected'
    start_time: str

    @classmethod
    def to_message(cls: Any, data: Any):
        return cls.parse_obj(data).dict()


class EventLogMessage(BaseModel):
    "Extract `EventData` based on schema"

    contract_event_name: ClassVar

    # The use of metaclasses complicates type-checking and inheritance, so to set a dynamic
    # class-property and type-checking annotations, we set it inside __init_subclass__.
    @classmethod
    def __init_subclass__(cls):
        cls.contract_event_name = cls.__name__
        super().__init_subclass__()

    @classmethod
    def extract(cls: Any, instance: Mapping):
        "Extract the fields indicated in schema from the event log message"
        return cls.parse_obj(instance).dict()


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
        from polyswarmd.app import app
        from polyswarmd.views.bounties import substitute_metadata
        config: Optional[Dict[str, Any]] = app.config
        ai = config['POLYSWARMD'].artifact.client
        session = FuturesSession(adapter_kwargs={'max_retries': 3})
        redis = config['POLYSWARMD'].redis.client

        def _substitute_metadata_impl(uri: str, validate=None):
            return substitute_metadata(uri, ai, session, validate=validate, redis=redis)

        cls._substitute_metadata = _substitute_metadata_impl

    @classmethod
    def fetch(cls, msg: WebsocketMessage,
              validate=AssertionMetadata.validate) -> WebsocketMessage:
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


def MessageField(*args, **kwargs):
    return Field(kwargs.get('default'), *args, **kwargs)


class Guid(str):

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        return cls(str(uuid.UUID(int=int(v))))


class ArtifactType(str):
    """The type for `ArtifactType`"""

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, int):
            return cls(_ArtifactType.to_string(_ArtifactType(v)))
        elif isinstance(v, str):
            return cls(v)
        else:
            raise ValueError(f"Could not build an ArtifactType from value provided: {v}")


EthereumAddr = constr(min_length=34, max_length=42)
Uint256 = int
BoolVector = List[bool]
BountyGuid = MessageField(alias='bountyGuid')

# 'from' is a reserved word in python, so it can't be used as an attribute of a class until this is
# changed, we just serialize the `_from` field to it's expeted value at serialization-time
From = MessageField(alias='from')


class Transfer(EventLogMessage):
    """Transfer

    doctest:

    >>> pprint(Transfer.extract({'to': addr1, 'from': addr2, 'value': 1 }))
    {'from': '0x00000000000000000000000000000002',
     'to': '0x00000000000000000000000000000001',
     'value': '1'}
    """

    to: EthereumAddr
    value: str
    from_: EthereumAddr = From

    def dict(self, *args, **kwargs):
        return super().dict(by_alias=True, *args, **kwargs)


class NewDeposit(EventLogMessage):
    """NewDeposit

    doctest:

    >>> NewDeposit.extract({'from': addr2, 'value': 1 })
    {'value': 1, 'from': '0x00000000000000000000000000000002'}
    >>> NewDeposit.contract_event_name
    'NewDeposit'
    """
    value: Uint256
    from_: EthereumAddr = From

    def dict(self, *args, **kwargs):
        return super().dict(by_alias=True, *args, **kwargs)


class NewWithdrawal(EventLogMessage):
    """NewWithdrawal

    doctest:

    >>> NewWithdrawal.extract({'to': addr1, 'from': addr2, 'value': 1 })
    {'to': '0x00000000000000000000000000000001', 'value': 1}
    >>> NewWithdrawal.contract_event_name
    'NewWithdrawal'
    """
    to: EthereumAddr
    value: Uint256


class OpenedAgreement(EventLogMessage):
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


class CanceledAgreement(EventLogMessage):

    @classmethod
    def extract(_cls, instance):
        return dict(instance)


class JoinedAgreement(EventLogMessage):

    @classmethod
    def extract(_cls, instance):
        return dict(instance)


class WebsocketFilterEvent(WebsocketMessage, EventLogMessage):
    @classmethod
    def collect_boolvectors(cls, event):
        if 'numArtifacts' in event:
            for attr, typ in cls.__annotations__.items():
                if typ == BoolVector and attr in event:
                    event[attr] = safe_int_to_bool_list(event[attr], event['numArtifacts'])
        return event

    @classmethod
    def to_message(cls: Any, data: Any):
        return WebsocketFilterMessage.parse_obj(dict(
            event=cls.event_id,
            block_number=data['blockNumber'],
            txhash=data['transactionHash'].hex(),
            data=cls.parse_obj(cls.collect_boolvectors(data['args']))
        )).dict()


class WebsocketFilterMessage(WebsocketMessage):
    event: str
    block_number: int
    txhash: str
    data: WebsocketFilterEvent


class FeesUpdated(WebsocketFilterEvent):
    """FeesUpdated

    doctest:

    >>> event = mkevent({'bountyFee': 5000000000000000, 'assertionFee': 5000000000000000 })
    >>> decoded_msg(FeesUpdated.serialize_message(event))
    {'block_number': 117,
     'data': {'assertion_fee': 5000000000000000, 'bounty_fee': 5000000000000000},
     'event': 'fee_update',
     'txhash': '0000000000000000000000000000000b'}
    """
    event_id: ClassVar[str] = 'fee_update'

    bounty_fee: int = MessageField(alias='bountyFee')
    assertion_fee: int = MessageField(alias='assertionFee')


class WindowsUpdated(WebsocketFilterEvent):
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
    event_id: ClassVar[str] = 'window_update'

    assertion_reveal_window: Uint256 = MessageField(alias='assertionRevealWindow')
    arbiter_vote_window: Uint256 = MessageField(alias='arbiterVoteWindow')


class NewBounty(WebsocketFilterEvent):
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
    event_id: ClassVar[str] = 'bounty'
    guid: Guid
    artifact_type: ArtifactType = Field('FILE', alias='artifactType')
    author: EthereumAddr
    amount: str
    uri: str = MessageField(alias='artifactURI')
    expiration: str = MessageField(alias='expirationBlock')
    metadata: str

    @classmethod
    def to_message(cls, event) -> WebsocketMessage:
        return MetadataHandler.fetch(super().to_message(event), validate=BountyMetadata.validate)


class NewAssertion(WebsocketFilterEvent):
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
    event_id: ClassVar[str] = 'assertion'

    bounty_guid: Guid = BountyGuid
    author: EthereumAddr
    index: Uint256
    bid: List[str]
    mask: BoolVector
    commitment: str


class RevealedAssertion(WebsocketFilterEvent):
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
    event_id: ClassVar[str] = 'reveal'

    bounty_guid: Guid = BountyGuid
    author: EthereumAddr
    index: Uint256
    nonce: str
    verdicts: BoolVector
    metadata: Any

    @classmethod
    def to_message(cls: Any, event: EventData):
        return MetadataHandler.fetch(super().to_message(event), validate=AssertionMetadata.validate)


class NewVote(WebsocketFilterEvent):
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
    event_id: ClassVar[str] = 'vote'
    bounty_guid: Guid = BountyGuid
    voter: EthereumAddr
    votes: BoolVector


class QuorumReached(WebsocketFilterEvent):
    """QuorumReached

    doctest:

    >>> event = mkevent({'bountyGuid': 16577})
    >>> decoded_msg(QuorumReached.serialize_message(event))
    {'block_number': 117,
     'data': {'bounty_guid': '00000000-0000-0000-0000-0000000040c1'},
     'event': 'quorum',
     'txhash': '0000000000000000000000000000000b'}
    """
    event_id: ClassVar[str] = 'quorum'
    bounty_guid: Guid = BountyGuid


class SettledBounty(WebsocketFilterEvent):
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
    event_id: ClassVar[str] = 'settled_bounty'
    bounty_guid: Guid = BountyGuid
    settler: EthereumAddr
    payout: Uint256


class InitializedChannel(WebsocketFilterEvent):
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
    event_id: ClassVar[str] = 'initialized_channel'
    ambassador: EthereumAddr
    expert: EthereumAddr
    guid: Guid
    multi_signature: EthereumAddr = MessageField(alias='msig')


class ClosedAgreement(WebsocketFilterEvent):
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
    event_id: ClassVar[str] = 'closed_agreement'
    ambassador: EthereumAddr = MessageField(alias='_ambassador')
    expert: EthereumAddr = MessageField(alias='_expert')


class StartedSettle(WebsocketFilterEvent):
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
    event_id: ClassVar[str] = 'settle_started'
    initiator: EthereumAddr
    nonce: Uint256 = MessageField(alias='sequence')
    settle_period_end: Uint256 = MessageField(alias='settlementPeriodEnd')


class SettleStateChallenged(WebsocketFilterEvent):
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
    event_id: ClassVar[str] = 'settle_challenged'

    challenger: EthereumAddr
    nonce: Uint256 = MessageField(alias='sequence')
    settle_period_end: Uint256 = MessageField(alias='settlementPeriodEnd')


class Deprecated(WebsocketFilterEvent):
    """Deprecated

    doctest:

    >>> event = mkevent({'rollover': True})
    >>> Deprecated.contract_event_name
    'Deprecated'
    >>> decoded_msg(Deprecated.serialize_message(event))
    {'block_number': 117,
     'data': {'rollover': True},
     'event': 'deprecated',
     'txhash': '0000000000000000000000000000000b'}
    """
    event_id: ClassVar[str] = 'deprecated'
    rollover: bool


class Undeprecated(WebsocketFilterEvent):
    """Undeprecated

    doctest:

    >>> Undeprecated.contract_event_name
    'Undeprecated'
    >>> event = mkevent({'a': 1, 'hello': 'world', 'should_not_be_here': True})
    >>> decoded_msg(Undeprecated.serialize_message(event))
    {'block_number': 117,
     'data': {},
     'event': 'undeprecated',
     'txhash': '0000000000000000000000000000000b'}
    """
    event_id: ClassVar[str] = 'undeprecated'


class LatestEvent(WebsocketFilterEvent):
    """LatestEvent

    doctest:

    >>> LE = LatestEvent.make(chain1)
    >>> LA = LatestEvent.make(chain2)
    >>> event = mkevent({'a': 1, 'hello': 'world', 'should_not_be_here': True})
    >>> LE.contract_event_name
    'latest'
    >>> LA.contract_event_name
    'latest'
    >>> decoded_msg(LE.serialize_message(event))
    {'data': {'number': 117}, 'event': 'block'}
    >>> decoded_msg(LA.serialize_message(event))
    {'data': {'number': 220}, 'event': 'block'}
    """
    event_id: ClassVar[str] = 'block'
    contract_event_name: ClassVar = 'latest'
    _chain: ClassVar[Any]

    @classmethod
    def to_message(cls, event):
        return {'event': cls.event_id, 'data': {'number': cls._chain.blockNumber}}

    @classmethod
    def make(cls, chain):
        ncls: Type[LatestEvent] = type(
            f'LatestEvent_{id(chain)}', LatestEvent.__bases__, dict(LatestEvent.__dict__)
        )
        ncls.contract_event_name = 'latest'
        ncls._chain = chain
        return ncls
