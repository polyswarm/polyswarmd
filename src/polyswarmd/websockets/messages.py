from typing import (TYPE_CHECKING, Any, ClassVar, Dict, List, Mapping, NewType, Optional, cast, Callable)
import ujson as json

from requests_futures.sessions import FuturesSession

from polyswarmartifact import ArtifactType
from polyswarmartifact.schema import Assertion as AssertionMetadata
from polyswarmartifact.schema import Bounty as BountyMetadata

from .json_schema import PSJSONSchema, SchemaDef, SchemaExtraction

if TYPE_CHECKING:
    try:
        from typing import TypedDict
    except ImportError:
        from mypy_extensions import TypedDict

    Hash32 = NewType('Hash32', bytes)
    HexAddress = NewType('HexAddress', str)
    ChecksumAddress = NewType('ChecksumAddress', HexAddress)

    # @type_check_only
    class EventData:
        args: Dict[str, Any]
        event: str
        logIndex: int
        transactionIndex: int
        transactionHash: Hash32
        address: ChecksumAddress
        blockHash: Hash32
        blockNumber: int

    class _BaseMessage(TypedDict):
        event: str
        data: Any

    class WebsocketMessageDict(_BaseMessage, total=False):
        block_number: Optional[int]
        txhash: Optional[str]
else:
    EventData = Dict[Any, Any]
    WebsocketMessageDict = Dict[Any, Any]


class WebsocketMessage:
    "Represent a message that can be handled by polyswarm-client"
    # This is the identifier used when building a websocket event identifier.
    event: ClassVar[str]
    __slots__ = ('message')

    def __init__(self, data=None):
        self.message = json.dumps(self.to_message(data)).encode('ascii')

    def to_message(self, data) -> WebsocketMessageDict:
        return {'event': self.event, 'data': data}

    def __bytes__(self) -> bytes:
        return self.message


class Connected(WebsocketMessage):
    event = 'connected'


class EventLogMessage:
    "Extract `EventData` based on schema"

    schema: ClassVar[PSJSONSchema]
    contract_event_name: ClassVar[str]

    # The use of metaclasses complicates type-checking and inheritance, so to set a dynamic
    # class-property and type-checking annotations, we set it inside __init_subclass__.
    @classmethod
    def __init_subclass__(cls):
        super().__init_subclass__()
        cls.contract_event_name = cls.__name__
        # extract the annotations from the jsonschema attached to the class (schema)
        if TYPE_CHECKING and 'schema' in cls.__dict__:
            cls.__annotations__ = cls.schema.build_annotations()

    @classmethod
    def extract(cls, instance: Mapping[Any, Any]) -> SchemaExtraction:
        "Extract the fields indicated in schema from the event log message"
        return cls.schema.extract(instance)


# Commonly used schema properties
uint256: SchemaDef = {'type': 'integer'}
guid: SchemaDef = {'type': 'string', 'format': 'uuid'}
bounty_guid: SchemaDef = cast(SchemaDef, {**guid, 'srckey': 'bountyGuid'})
ethereum_address: SchemaDef = {'type': 'string', 'format': 'ethaddr'}


# The fetch routine uses format to split into a bitvector, e.g format(16, "0>10b") => '0000010000'
def int_to_boolvector(x: int, sz: int) -> List[bool]:
    return [b != '0' for b in format(x, "0>" + str(sz) + "b")]


boolvector: SchemaDef = {
    'type': 'array',
    'items': 'boolean',
    'srckey': lambda k, e: int_to_boolvector(int(e[k]), e.numArtifacts)
}


# partially applied `substitute_metadata' with AI, redis & session prefilled.
_substitute_metadata: Optional[Callable[[str, bool], Any]] = None


def fetch_metadata(msg: WebsocketMessageDict, validate=None) -> WebsocketMessageDict:
    """Fetch metadata with URI from `msg', validate it and merge the result

    >>> global _substitute_metadata
    >>> _substitute_metadata = lambda uri, validate: { 'hello': uri }
    >>> msg = {'event': 'test', 'data': { 'metadata': 'uri' }}
    >>> fetch_metadata(msg, override=_substitute_metadata)
    {'event': 'test', 'data': {'metadata': {'hello': 'uri'}}}
    """
    data = msg.get('data')
    if not data:
        return msg

    global _substitute_metadata
    if not _substitute_metadata:
        from polyswarmd import app
        from polyswarmd.bounties import substitute_metadata
        config: Optional[Dict[str, Any]] = app.config
        ai = config['POLYSWARMD'].artifact_client
        session = FuturesSession(adapter_kwargs={'max_retries': 3})
        redis = config['POLYSWARMD'].redis

        def _substitute_metadata(uri: str, validate):
            return substitute_metadata(uri, ai, session, validate=validate, redis=redis)

    data.update(metadata=_substitute_metadata(data.get('metadata'), validate))
    return msg


class Transfer(EventLogMessage):
    schema = PSJSONSchema({
        'properties': {
            'to': ethereum_address,
            'from': ethereum_address,
            'value': {
                'type': 'string'
            }
        }
    })


class NewDeposit(EventLogMessage):
    schema = PSJSONSchema({'properties': {
        'value': uint256,
        'from': ethereum_address,
    }})


class NewWithdrawal(EventLogMessage):
    schema = PSJSONSchema({'properties': {
        'to': ethereum_address,
        'value': uint256,
    }})


def second_argument_to_dict(_ignore, obj):
    return dict(obj)


extract_as_dict = {'extract': second_argument_to_dict}
# The classes below have no defined extraction ('conversion') logic,
# so they simply return the argument to `extract` as a `dict`
OpenedAgreement = type('OpenedAgreement', (EventLogMessage,), extract_as_dict)
CanceledAgreement = type('CanceledAgreement', (EventLogMessage,), extract_as_dict)
JoinedAgreement = type('JoinedAgreement', (EventLogMessage,), extract_as_dict)


class WebsocketFilterMessage(WebsocketMessage, EventLogMessage):
    """Websocket message interface for etherem event entries. """
    event: ClassVar[str]
    schema: ClassVar[PSJSONSchema]
    contract_event_name: ClassVar[str]

    __slots__ = ('message')

    def to_message(self, event: EventData) -> WebsocketMessageDict:
        return {
            'event': self.event,
            'data': self.extract(event.args),
            'block_number': event.blockNumber,
            'txhash': event.transactionHash.hex()
        }

    def __repr__(self):
        return f'<{self.contract_event_name} name={self.event}>'


class FeesUpdated(WebsocketFilterMessage):
    event = 'fee_update'
    schema = PSJSONSchema({
        'properties': {
            'bounty_fee': {
                **uint256, 'srckey': 'bountyFee'
            },
            'assertion_fee': {
                **uint256, 'srckey': 'assertionFee'
            }
        },
    })


class WindowsUpdated(WebsocketFilterMessage):
    event = 'window_update'
    schema = PSJSONSchema({
        'properties': {
            'assertion_reveal_window': {
                **uint256, 'srckey': 'assertionRevealWindow'
            },
            'arbiter_vote_window': {
                **uint256, 'srckey': 'arbiterVoteWindow'
            }
        }
    })


class NewBounty(WebsocketFilterMessage):
    event = 'bounty'
    schema = PSJSONSchema({
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
                'type': 'string',
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

    def to_message(self, event: EventData) -> WebsocketMessageDict:
        return fetch_metadata(super().to_message(event), validate=BountyMetadata.validate)


class NewAssertion(WebsocketFilterMessage):
    event = 'assertion'
    schema = PSJSONSchema({
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


class RevealedAssertion(WebsocketFilterMessage):
    event = 'reveal'
    schema = PSJSONSchema({
        'properties': {
            'bounty_guid': bounty_guid,
            'author': ethereum_address,
            'index': uint256,
            'nonce': {
                'type': 'string',
            },
            'verdicts': boolvector,
            'metadata': {
                'type': 'string'
            }
        }
    })

    def to_message(self, event: EventData) -> WebsocketMessageDict:
        return fetch_metadata(super().to_message(event), validate=AssertionMetadata.validate)


class NewVote(WebsocketFilterMessage):
    event = 'vote'
    schema = PSJSONSchema({
        'properties': {
            'bounty_guid': bounty_guid,
            'voter': ethereum_address,
            'votes': boolvector
        }
    })


class QuorumReached(WebsocketFilterMessage):
    event = 'quorum'
    schema = PSJSONSchema({'properties': {'bounty_guid': bounty_guid}})


class SettledBounty(WebsocketFilterMessage):
    event = 'settled_bounty'
    schema = PSJSONSchema({
        'properties': {
            'bounty_guid': bounty_guid,
            'settler': ethereum_address,
            'payout': uint256
        }
    })


class InitializedChannel(WebsocketFilterMessage):
    event = 'initialized_channel'
    schema = PSJSONSchema({
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


class ClosedAgreement(WebsocketFilterMessage):
    event = 'closed_agreement'
    schema = PSJSONSchema({
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


class StartedSettle(WebsocketFilterMessage):
    event = 'settle_started'
    schema = PSJSONSchema({
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


class SettleStateChallenged(WebsocketFilterMessage):
    event = 'settle_challenged'
    schema = PSJSONSchema({
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


class Deprecated(WebsocketFilterMessage):
    event = 'deprecated'

    def to_message(self, event: EventData):
        return {}


class LatestEvent(WebsocketFilterMessage):
    event = 'block'
    contract_event_name = 'latest'
    _chain: ClassVar[Any]

    def to_message(self, event: Any):
        return {'event': self.event, 'data': {'number': self.block_number}}

    @property
    def block_number(self):
        return self._chain.blockNumber

    @classmethod
    def make(cls, chain):
        cls._chain = chain
        return cls
