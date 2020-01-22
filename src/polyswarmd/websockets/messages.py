from typing import (
    Any,
    ClassVar,
    Dict,
    Generic,
    List,
    Mapping,
    Optional,
    Type,
    TypeVar,
    cast,
    get_type_hints,
)

from pydantic import BaseModel
from pydantic.generics import GenericModel
import ujson

from polyswarmartifact.schema import Assertion, Bounty
from polyswarmd.utils import safe_int_to_bool_list
from polyswarmd.websockets.types import (
    ArtifactMetadata,
    ArtifactTypeField,
    BoolVector,
    BountyGuid,
    EthereumAddress,
    EventData,
    EventGUID,
    EventId,
    TXID,
    From,
    MessageField,
    To,
    TypeVarType,
    Uint256,
)

EventDataT = TypeVar('EventDataT', bound='BaseEvent')


class WebsocketSerializable:
    __event__: ClassVar[str]

    @classmethod
    def serialize_message(cls: Any, data: Any) -> bytes:
        return ujson.dumps(cls.to_message(data)).encode('ascii')

    @classmethod
    def to_message(cls, data: Any):
        return {'event': cls.__event__, 'data': data}


class WebsocketMessage(GenericModel, Generic[EventDataT], WebsocketSerializable):
    "Represent a message that can be handled by polyswarm-client"
    event: EventId
    data: EventDataT
    block_number: Uint256
    txhash: TXID

    @classmethod
    def event_type(cls) -> Type[EventDataT]:
        return get_type_hints(cls)['data']

    @classmethod
    def to_message(cls, data: EventData) -> Dict:
        return cls.from_event(data).dict()

    @classmethod
    def from_event(cls, data: EventData) -> 'WebsocketMessage[EventDataT]':
        event_type = cls.event_type()
        return cls(
            event=event_type.__event__,
            block_number=data['blockNumber'],
            txhash=data['transactionHash'].hex(),
            data=event_type.parse_obj(data.get('args'))
        )


class BaseEvent(WebsocketSerializable, BaseModel):
    __event__: ClassVar[EventId]
    event_types: ClassVar[Dict[EventId, Type]] = {}

    # The use of metaclasses complicates type-checking and inheritance, so to set a dynamic
    # class-property and type-checking annotations, we set it inside __init_subclass__.
    @classmethod
    def __init_subclass__(cls):
        if hasattr(cls, '__event__'):
            BaseEvent.event_types[cls.__event__] = cls
        super().__init_subclass__()

    @classmethod
    def to_message(cls: Type, data: EventData) -> Dict:
        type_var: TypeVarType = cast(TypeVarType, cls)
        return WebsocketMessage[type_var].to_message(data)


class ContractEvent(BaseEvent):
    contract_event_name: ClassVar

    # The use of metaclasses complicates type-checking and inheritance, so to set a dynamic
    # class-property and type-checking annotations, we set it inside __init_subclass__.
    @classmethod
    def __init_subclass__(cls):
        cls.contract_event_name = cls.__name__
        super().__init_subclass__()

    def __init__(self, *args, **kwargs):
        # build the BoolVector ahead of time
        if 'numArtifacts' in kwargs:
            for attr, typ in self.__annotations__.items():
                if typ == BoolVector and attr in kwargs:
                    kwargs[attr] = safe_int_to_bool_list(kwargs[attr], kwargs['numArtifacts'])

        super().__init__(*args, **kwargs)

    @classmethod
    def extract(cls: Any, instance: Mapping):
        "Extract the fields indicated in schema from the event log message"
        return cls.parse_obj(instance).dict()


class Connected(BaseEvent):
    __event__: ClassVar[EventId] = 'connected'
    start_time: str


class Transfer(ContractEvent):
    """Transfer

    doctest:

    >>> pprint(Transfer.extract({'to': addr1, 'from': addr2, 'value': 1 }))
    {'from': '0x0000000000000000000000000000000000000002',
     'to': '0x0000000000000000000000000000000000000001',
     'value': '1'}
    """
    recipient: EthereumAddress = To
    value: str
    sender: EthereumAddress = From

    def dict(self, *args, **kwargs):
        return super().dict(by_alias=True, *args, **kwargs)


class NewDeposit(ContractEvent):
    """NewDeposit

    doctest:

    >>> NewDeposit.extract({'from': addr2, 'value': 1 })
    {'value': 1, 'from': '0x0000000000000000000000000000000000000002'}
    >>> NewDeposit.contract_event_name
    'NewDeposit'
    """
    value: Uint256
    sender: EthereumAddress = From

    def dict(self, *args, **kwargs):
        return super().dict(by_alias=True, *args, **kwargs)


class NewWithdrawal(ContractEvent):
    """NewWithdrawal

    doctest:

    >>> NewWithdrawal.extract({'to': addr1, 'from': addr2, 'value': 1 })
    {'to': '0x0000000000000000000000000000000000000001', 'value': 1}
    >>> NewWithdrawal.contract_event_name
    'NewWithdrawal'
    """
    recipient: EthereumAddress = To
    value: Uint256

    def dict(self, *args, **kwargs):
        return super().dict(by_alias=True, *args, **kwargs)


class OpenedAgreement(ContractEvent):
    """OpenedAgreement

    doctest:

    >>> pprint(OpenedAgreement.extract({ 'to': addr1, 'from': addr2, 'value': 1 }))
    {'from': '0x0000000000000000000000000000000000000002',
     'to': '0x0000000000000000000000000000000000000001',
     'value': 1}
    >>> OpenedAgreement.contract_event_name
    'OpenedAgreement'
    """

    @classmethod
    def extract(_cls, instance):
        return dict(instance)


class CanceledAgreement(ContractEvent):

    @classmethod
    def extract(_cls, instance):
        return dict(instance)


class JoinedAgreement(ContractEvent):

    @classmethod
    def extract(_cls, instance):
        return dict(instance)


class FeesUpdated(ContractEvent):
    """FeesUpdated

    doctest:

    >>> event = mkevent({'bountyFee': 5000000000000000, 'assertionFee': 5000000000000000 })
    >>> decoded_msg(FeesUpdated.serialize_message(event))
    {'block_number': 117,
     'data': {'assertion_fee': 5000000000000000, 'bounty_fee': 5000000000000000},
     'event': 'fee_update',
     'txhash': '000000000000000000000000000000000000000000000000000000000000000b'}
    >>> FeesUpdated.contract_event_name
    'FeesUpdated'
    """
    __event__: ClassVar[EventId] = 'fee_update'

    bounty_fee: int = MessageField(alias='bountyFee')
    assertion_fee: int = MessageField(alias='assertionFee')


class WindowsUpdated(ContractEvent):
    """WindowsUpdated

    doctest:

    >>> event = mkevent({
    ... 'assertionRevealWindow': 100,
    ... 'arbiterVoteWindow': 105 })
    >>> decoded_msg(WindowsUpdated.serialize_message(event))
    {'block_number': 117,
     'data': {'arbiter_vote_window': 105, 'assertion_reveal_window': 100},
     'event': 'window_update',
     'txhash': '000000000000000000000000000000000000000000000000000000000000000b'}
    """
    __event__: ClassVar[EventId] = 'window_update'

    assertion_reveal_window: Uint256 = MessageField(alias='assertionRevealWindow')
    arbiter_vote_window: Uint256 = MessageField(alias='arbiterVoteWindow')


class NewBounty(ContractEvent):
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
              'author': '0x0000000000000000000000000000000000000001',
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
     'txhash': '000000000000000000000000000000000000000000000000000000000000000b'}
    """
    __event__: ClassVar[EventId] = 'bounty'
    guid: EventGUID
    artifact_type: ArtifactTypeField = MessageField(alias='artifactType')
    author: EthereumAddress
    amount: str
    uri: str = MessageField(alias='artifactURI')
    expiration: str = MessageField(alias='expirationBlock')
    metadata: ArtifactMetadata[Bounty]


class NewAssertion(ContractEvent):
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
     'txhash': '000000000000000000000000000000000000000000000000000000000000000b'}
    """
    __event__: ClassVar[EventId] = 'assertion'

    bounty_guid: EventGUID = BountyGuid
    author: EthereumAddress
    index: Uint256
    bid: List[str]
    mask: BoolVector
    commitment: str


class RevealedAssertion(ContractEvent):
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
     'txhash': '000000000000000000000000000000000000000000000000000000000000000b'}
    """
    __event__: ClassVar[EventId] = 'reveal'

    bounty_guid: EventGUID = BountyGuid
    author: EthereumAddress
    index: Uint256
    nonce: str
    verdicts: BoolVector
    metadata: ArtifactMetadata[Assertion]


class NewVote(ContractEvent):
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
     'txhash': '000000000000000000000000000000000000000000000000000000000000000b'}
    """
    __event__: ClassVar[EventId] = 'vote'
    bounty_guid: EventGUID = BountyGuid
    voter: EthereumAddress
    votes: BoolVector


class QuorumReached(ContractEvent):
    """QuorumReached

    doctest:

    >>> event = mkevent({'bountyGuid': 16577})
    >>> decoded_msg(QuorumReached.serialize_message(event))
    {'block_number': 117,
     'data': {'bounty_guid': '00000000-0000-0000-0000-0000000040c1'},
     'event': 'quorum',
     'txhash': '000000000000000000000000000000000000000000000000000000000000000b'}
    """
    __event__: ClassVar[EventId] = 'quorum'
    bounty_guid: EventGUID = BountyGuid


class SettledBounty(ContractEvent):
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
              'settler': '0x0000000000000000000000000000000000000001'},
     'event': 'settled_bounty',
     'txhash': '000000000000000000000000000000000000000000000000000000000000000b'}
    """
    __event__: ClassVar[EventId] = 'settled_bounty'
    bounty_guid: EventGUID = BountyGuid
    settler: EthereumAddress
    payout: Uint256


class InitializedChannel(ContractEvent):
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
     'txhash': '000000000000000000000000000000000000000000000000000000000000000b'}
    """
    __event__: ClassVar[EventId] = 'initialized_channel'
    ambassador: EthereumAddress
    expert: EthereumAddress
    guid: EventGUID
    multi_signature: EthereumAddress = MessageField(alias='msig')


class ClosedAgreement(ContractEvent):
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
     'txhash': '000000000000000000000000000000000000000000000000000000000000000b'}
    """
    __event__: ClassVar[EventId] = 'closed_agreement'
    ambassador: EthereumAddress = MessageField(alias='_ambassador')
    expert: EthereumAddress = MessageField(alias='_expert')


class StartedSettle(ContractEvent):
    """StartedSettle

    doctest:

    >>> event = mkevent({
    ... 'initiator': addr1,
    ... 'sequence': 1688,
    ... 'settlementPeriodEnd': 229 })
    >>> decoded_msg(StartedSettle.serialize_message(event))
    {'block_number': 117,
     'data': {'initiator': '0x0000000000000000000000000000000000000001',
              'nonce': 1688,
              'settle_period_end': 229},
     'event': 'settle_started',
     'txhash': '000000000000000000000000000000000000000000000000000000000000000b'}

    """
    __event__: ClassVar[EventId] = 'settle_started'
    initiator: EthereumAddress
    nonce: Uint256 = MessageField(alias='sequence')
    settle_period_end: Uint256 = MessageField(alias='settlementPeriodEnd')


class SettleStateChallenged(ContractEvent):
    """SettleStateChallenged

    doctest:

    >>> event = mkevent({
    ... 'challenger': addr1,
    ... 'sequence': 1688,
    ... 'settlementPeriodEnd': 229 })
    >>> decoded_msg(SettleStateChallenged.serialize_message(event))
    {'block_number': 117,
     'data': {'challenger': '0x0000000000000000000000000000000000000001',
              'nonce': 1688,
              'settle_period_end': 229},
     'event': 'settle_challenged',
     'txhash': '000000000000000000000000000000000000000000000000000000000000000b'}
    """
    __event__: ClassVar[EventId] = 'settle_challenged'

    challenger: EthereumAddress
    nonce: Uint256 = MessageField(alias='sequence')
    settle_period_end: Uint256 = MessageField(alias='settlementPeriodEnd')


class Deprecated(ContractEvent):
    """Deprecated

    doctest:

    >>> event = mkevent({'rollover': True})
    >>> Deprecated.contract_event_name
    'Deprecated'
    >>> decoded_msg(Deprecated.serialize_message(event))
    {'block_number': 117,
     'data': {'rollover': True},
     'event': 'deprecated',
     'txhash': '000000000000000000000000000000000000000000000000000000000000000b'}
    """
    __event__: ClassVar[EventId] = 'deprecated'
    rollover: bool


class Undeprecated(ContractEvent):
    """Undeprecated

    doctest:

    >>> Undeprecated.contract_event_name
    'Undeprecated'
    >>> event = mkevent({'a': 1, 'hello': 'world', 'should_not_be_here': True})
    >>> decoded_msg(Undeprecated.serialize_message(event))
    {'block_number': 117,
     'data': {},
     'event': 'undeprecated',
     'txhash': '000000000000000000000000000000000000000000000000000000000000000b'}
    """
    __event__: ClassVar[EventId] = 'undeprecated'


class LatestEvent(ContractEvent):
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
    __event__: ClassVar[EventId] = 'block'
    contract_event_name: ClassVar = 'latest'
    _chain: ClassVar[Any]

    @classmethod
    def to_message(cls, event):
        return {'event': cls.__event__, 'data': {'number': cls._chain.blockNumber}}

    @classmethod
    def make(cls, chain):
        ncls: Type[LatestEvent] = type(
            f'LatestEvent_{id(chain)}', LatestEvent.__bases__, dict(LatestEvent.__dict__)
        )
        ncls.contract_event_name = 'latest'
        ncls._chain = chain
        return ncls
