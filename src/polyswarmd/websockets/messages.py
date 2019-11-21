from functools import lru_cache
from typing import TYPE_CHECKING, Any, ClassVar, Dict, List, Mapping, NewType, Optional, cast

from polyswarmartifact import ArtifactType
from polyswarmartifact.schema import Assertion as AssertionMetadata, Bounty as BountyMetadata
from requests_futures.sessions import FuturesSession
import ujson as json

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

    @classmethod
    def __init_subclass__(cls):
        super().__init_subclass__()
        cls.contract_event_name = cls.__name__
        if 'schema' in cls.__dict__:
            if TYPE_CHECKING:
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

# The functions below are commented out because they depend on configuration being loaded from PolyswarmD.

session = FuturesSession(adapter_kwargs={'max_retries': 3})

config: Optional[Dict[str, Any]] = None
artifact_client = None
redis = None


# XXX this is about as hacky as it gets. We should extract configuration loading out.
@lru_cache(15)
def fetch_metadata(uri: str, validate):
    from polyswarmd.bounties import substitute_metadata
    global config
    global redis
    global artifact_client
    if config is None:
        from polyswarmd import app
        config = app.config
    artifact_client = config['POLYSWARMD'].artifact_client
    redis = config['POLYSWARMD'].redis
    return substitute_metadata(uri, artifact_client, session, validate=validate, redis=redis)


def pull_metadata(data, validate=None):
    if 'metadata' in data:
        data['metadata'] = fetch_metadata(data['metadata'], validate)
    return data


class Transfer(EventLogMessage):
    schema = PSJSONSchema(
        {'properties': {
            'to': ethereum_address,
            'from': ethereum_address,
            'value': {
                'type': 'string'
            }
        }})


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
OpenedAgreement = type('OpenedAgreement', (EventLogMessage, ), extract_as_dict)
CanceledAgreement = type('CanceledAgreement', (EventLogMessage, ), extract_as_dict)
JoinedAgreement = type('JoinedAgreement', (EventLogMessage, ), extract_as_dict)


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
        return {
            'event': self.event,
            'data': pull_metadata(self.extract(event.args), validate=BountyMetadata.validate),
            'block_number': event.blockNumber,
            'txhash': event.transactionHash.hex()
        }


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
        return {
            'event': self.event,
            'data': pull_metadata(self.extract(event.args), validate=AssertionMetadata.validate),
            'block_number': event.blockNumber,
            'txhash': event.transactionHash.hex()
        }


class NewVote(WebsocketFilterMessage):
    event = 'vote'
    schema = PSJSONSchema(
        {'properties': {
            'bounty_guid': bounty_guid,
            'voter': ethereum_address,
            'votes': boolvector
        }})


class QuorumReached(WebsocketFilterMessage):
    event = 'quorum'
    schema = PSJSONSchema({'properties': {'bounty_guid': bounty_guid}})


class SettledBounty(WebsocketFilterMessage):
    event = 'settled_bounty'
    schema = PSJSONSchema(
        {'properties': {
            'bounty_guid': bounty_guid,
            'settler': ethereum_address,
            'payout': uint256
        }})


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
