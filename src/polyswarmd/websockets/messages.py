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
    TXID,
    ArtifactMetadata,
    ArtifactTypeField,
    BoolVector,
    BountyGuid,
    EthereumAddress,
    EventData,
    EventGUID,
    EventId,
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
    recipient: EthereumAddress = To
    value: str
    sender: EthereumAddress = From

    def dict(self, *args, **kwargs):
        return super().dict(by_alias=True, *args, **kwargs)


class NewDeposit(ContractEvent):
    value: Uint256
    sender: EthereumAddress = From

    def dict(self, *args, **kwargs):
        return super().dict(by_alias=True, *args, **kwargs)


class NewWithdrawal(ContractEvent):
    recipient: EthereumAddress = To
    value: Uint256

    def dict(self, *args, **kwargs):
        return super().dict(by_alias=True, *args, **kwargs)


class OpenedAgreement(ContractEvent):

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
    __event__: ClassVar[EventId] = 'fee_update'

    bounty_fee: int = MessageField(alias='bountyFee')
    assertion_fee: int = MessageField(alias='assertionFee')


class WindowsUpdated(ContractEvent):
    __event__: ClassVar[EventId] = 'window_update'

    assertion_reveal_window: Uint256 = MessageField(alias='assertionRevealWindow')
    arbiter_vote_window: Uint256 = MessageField(alias='arbiterVoteWindow')


class NewBounty(ContractEvent):
    __event__: ClassVar[EventId] = 'bounty'
    guid: EventGUID
    artifact_type: ArtifactTypeField = MessageField(alias='artifactType')
    author: EthereumAddress
    amount: str
    uri: str = MessageField(alias='artifactURI')
    expiration: str = MessageField(alias='expirationBlock')
    metadata: Optional[ArtifactMetadata[Bounty]]


class NewAssertion(ContractEvent):
    __event__: ClassVar[EventId] = 'assertion'

    bounty_guid: EventGUID = BountyGuid
    author: EthereumAddress
    index: Uint256
    bid: List[str]
    mask: BoolVector
    commitment: str


class RevealedAssertion(ContractEvent):
    __event__: ClassVar[EventId] = 'reveal'

    bounty_guid: EventGUID = BountyGuid
    author: EthereumAddress
    index: Uint256
    nonce: str
    verdicts: BoolVector
    metadata: ArtifactMetadata[Assertion]


class NewVote(ContractEvent):
    __event__: ClassVar[EventId] = 'vote'
    bounty_guid: EventGUID = BountyGuid
    voter: EthereumAddress
    votes: BoolVector


class QuorumReached(ContractEvent):
    __event__: ClassVar[EventId] = 'quorum'
    bounty_guid: EventGUID = BountyGuid


class SettledBounty(ContractEvent):
    __event__: ClassVar[EventId] = 'settled_bounty'
    bounty_guid: EventGUID = BountyGuid
    settler: EthereumAddress
    payout: Uint256


class InitializedChannel(ContractEvent):
    __event__: ClassVar[EventId] = 'initialized_channel'
    ambassador: EthereumAddress
    expert: EthereumAddress
    guid: EventGUID
    multi_signature: EthereumAddress = MessageField(alias='msig')


class ClosedAgreement(ContractEvent):
    __event__: ClassVar[EventId] = 'closed_agreement'
    ambassador: EthereumAddress = MessageField(alias='_ambassador')
    expert: EthereumAddress = MessageField(alias='_expert')


class StartedSettle(ContractEvent):
    __event__: ClassVar[EventId] = 'settle_started'
    initiator: EthereumAddress
    nonce: Uint256 = MessageField(alias='sequence')
    settle_period_end: Uint256 = MessageField(alias='settlementPeriodEnd')


class SettleStateChallenged(ContractEvent):
    __event__: ClassVar[EventId] = 'settle_challenged'

    challenger: EthereumAddress
    nonce: Uint256 = MessageField(alias='sequence')
    settle_period_end: Uint256 = MessageField(alias='settlementPeriodEnd')


class Deprecated(ContractEvent):
    __event__: ClassVar[EventId] = 'deprecated'
    rollover: bool


class Undeprecated(ContractEvent):
    __event__: ClassVar[EventId] = 'undeprecated'


class LatestEvent(ContractEvent):
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
