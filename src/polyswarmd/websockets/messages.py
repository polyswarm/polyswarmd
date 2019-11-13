try:
    import ujson as json
except ImportError:
    import json

import uuid
from functools import lru_cache
from types import MappingProxyType
from typing import Any, Dict, List

from polyswarmartifact import ArtifactType
from polyswarmd import app
from polyswarmd.artifacts.ipfs import IpfsServiceClient
from polyswarmd.bounties import substitute_metadata
from redis import redis
from requests_futures.sessions import FuturesSession
from web3.utils import Event


class WebsocketMessage():
    "Represent a message that can be handled by polyswarm-client"
    # This is the identifier used when building a websocket event identifier.
    _ws_event: str
    __slots__ = ('data')

    @property
    def event(self) -> str:
        return self._ws_event

    def __init__(self, data={}):
        if not self._ws_event:
            raise ValueError("This class has no websocket event name")
        self.data = data

    def as_dict(self):
        "`as_dict' should return an object representing the websocket message that the client will consume"
        return {'event': self.event, 'data': self.data}

    def __str__(self):
        return json.dumps(self.as_dict())


class Connected(WebsocketMessage):
    _ws_event = 'connected'


JSONSchema = Any


def json_schema_extractor(schema: JSONSchema, source: Any) -> Dict[str, Any]:
    """Extract and format fields from a `source' object with jsonschema

    It extends jsonschema with several special keys that control extraction from `source`:

        $#fetch - Run a function with args=[source, key, property_schema]
        $#src - Extract this key from `source'

        If neither of these are present, it copies the value of source[key].

    Any properties with a `type` parameter will be converted to that type.
    """
    for key, pschema in schema['properties'].items():
        if '$#src' in pschema:
            value = source[pschema['$#src']], pschema
        elif '$#fetch' in pschema:
            fn = pschema['$#fetch']
            value = fn(source, key, pschema)
        else:
            value = source[pschema[key]]

        yield {key: format_type(value, pschema)}


def format_type(value: Any, schema: JSONSchema) -> Any:
    result = value

    def as_uuid() -> uuid.UUID:
        return uuid.UUID(int=value)

    formatters = {'uuid': as_uuid}

    if 'format' in schema:
        if schema['format'] in formatters:
            result = formatters[schema['format']](result)

    def decide_array():
        return [format_type(v, {'type': schema['items']}) for v in value]

    conversions = {'string': str, 'integer': int, 'number': float, 'array': decide_array, 'bool': bool}
    if 'type' in schema:
        if schema['type'] in conversions:
            result = conversions[schema['type']](result)

    return result


class WebsocketEventlogMessage(WebsocketMessage):
    """Websocket message interface for etherem event entries. """

    _ws_event: str
    _ws_schema: JSONSchema

    def __init__(self, event: Event):
        self.data = json_schema_extractor(self._ws_schema, MappingProxyType(event))

    def as_dict(self):
        return {'event': self.event_name, 'data': self.data, 'block_number': self.block_number, 'txhash': self.txhash}

    @property
    def filter_event(self) -> str:
        "The event name used by web3 (e.g 'Transfer' or 'FeesUpdated')"
        return self.__class__.__name__

    @property
    def event_name(self):
        return self._ws_event

    @property
    def block_number(self) -> int:
        return self.event.blockNumber

    @property
    def txhash(self) -> str:
        return self.event.transactionHash.hex()

    def __repr__(self):
        return f'<WebsocketEventlogMessage name={self._ws_event}>'


session = FuturesSession(adapter_kwargs={'max_retries': 3})


@lru_cache(15)
def fetch_metadata(uri: str,
                   validate=None,
                   artifact_client: IpfsServiceClient = app.config['POLYSWARMD'].artifact_client,
                   redis: redis = app.config['POLYSWARMD'].redis):
    return substitute_metadata(uri, artifact_client, session, validate, redis)


def as_bv(e: Event, k: str, *args) -> List[bool]:
    "Return the bitvector for a number, where 1 is 'True' and 0 is 'False'"
    return [True if b == '1' else False for b in format(e[k], f"0>{e.numArtifacts}b")]


guid = {
    'type': 'string',
    'format': 'uuid',
}

# bounty_guid = { '$ref': '#/defs/bounty_guid }
bounty_guid = {'type': 'string', 'format': 'uuid', '$#from': 'bountyGuid'}


class FeesUpdated(WebsocketEventlogMessage):
    _ws_event = 'fee_update'
    _ws_schema = {
        'properties': {
            'bounty_fee': {
                'type': 'integer',
            },
            'assertion_fee': {
                'type': 'integer',
            }
        },
    }


class WindowsUpdated(WebsocketEventlogMessage):
    _ws_event = 'window_update'
    _ws_schema = {
        'properties': {
            'assertion_reveal_window': {
                'type': 'integer',
                '$#src': 'assertionRevealWindow'
            },
            'arbiter_vote_window': {
                'type': 'integer',
                '$#src': 'arbiterVoteWindow'
            }
        }
    }


class NewBounty(WebsocketEventlogMessage):
    _ws_event = 'bounty'
    _ws_schema = {
        'properties': {
            'guid': guid,
            'artifact_type': {
                'type': 'string',
                'enum': ['file', 'url'],
                '$#fetch': lambda e: ArtifactType.to_string(ArtifactType(e.artifactType))
            },
            'author': {
                'type': 'string',
            },
            'amount': {
                'type': 'string'
            },
            'uri': {
                'type': 'string',
                '$#from': 'artifactURI'
            },
            'expiration': {
                'type': 'string',
                '$#from': 'expirationBlock'
            },
            'metadata': {
                'type': 'string',
                '$#fetch': lambda e, k, _: fetch_metadata(e['metadata'])
            }
        }
    }


class NewAssertion(WebsocketEventlogMessage):
    _ws_event = 'assertion'
    _ws_schema = {
        'properties': {
            'bounty_guid': bounty_guid,
            'author': {
                'type': 'string'
            },
            'index': {
                'type': 'string'
            },
            'bid': {
                'type': 'array',
                'items': 'string',
            },
            'mask': {
                'type': 'array',
                'items': 'bool',
                '$#fetch': as_bv
            },
            'commitment': {
                'type': 'string'
            },
        },
    }


class RevealedAssertion(WebsocketEventlogMessage):
    _ws_event = 'reveal'
    _ws_schema = {
        'properties': {
            'bounty_guid': bounty_guid,
            'author': {
                'type': 'string'
            },
            'index': {
                'type': 'string'
            },
            'nonce': {
                'type': 'string'
            },
            'verdicts': {
                'type': 'array',
                'items': 'boolean',
                '$#fetch': as_bv
            },
            'metadata': {
                'type': 'object',
                '$#fetch': lambda e, k, _: fetch_metadata(e['metadata'])
            }
        }
    }


class NewVote(WebsocketEventlogMessage):
    _ws_event = 'vote'
    _ws_schema = {
        'properties': {
            'bounty_guid': bounty_guid,
            'voter': {
                'type': 'string'
            },
            'votes': {
                '$#fetch': as_bv,
                'items': 'bool',
                'type': 'array'
            }
        }
    }


class QuorumReached(WebsocketEventlogMessage):
    _ws_event = 'quorum'
    _ws_schema = {'properties': {'bounty_guid': bounty_guid, 'to': {'type': 'string'}, 'from': {'type': 'string'}}}


class SettledBounty(WebsocketEventlogMessage):
    _ws_event = 'settled_bounty'
    _ws_schema = {
        'properties': {
            'bounty_guid': bounty_guid,
            'settler': {
                'type': 'string'
            },
            'payout': {
                'type': 'string'
            }
        }
    }


class Deprecated(WebsocketEventlogMessage):
    _ws_event = 'deprecated'

    def __init__(self, *args):
        self.data = {}


class InitializedChannel(WebsocketEventlogMessage):
    _ws_event = 'initialized_channel'
    _ws_schema = {
        'properties': {
            'ambassador': {
                'type': 'string'
            },
            'expert': {
                'type': 'string'
            },
            'guid': guid,
            'multi_signature': {
                '$#from': 'msig',
                'type': 'string'
            }
        }
    }


class LatestEvent(WebsocketEventlogMessage):
    _ws_event = 'block'
    filter_event = 'latest'

    def as_dict(self):
        return {'event': self.name, 'data': {'number': self.block_number}}


class ClosedAgreement(WebsocketEventlogMessage):
    _ws_event = 'closed_agreement'
    _ws_schema = {
        'properties': {
            'ambassador': {
                '$#from': '_ambassador',
                'type': 'string'
            },
            'expert': {
                '$#from': '_expert',
                'type': 'string'
            }
        }
    }


class StartedSettle(WebsocketEventlogMessage):
    _ws_event = 'settle_started'
    _ws_schema = {
        'properties': {
            'initiator': {
                'type': 'string'
            },
            'nonce': {
                '$#from': 'sequence',
                'type': 'string'
            },
            'settle_period_end': {
                '$#from': 'settlementPeriodEnd',
                'type': 'string'
            }
        }
    }


class SettleStateChallenged(WebsocketEventlogMessage):
    _ws_event = 'settle_challenged'
    _ws_schema = {
        'properties': {
            'challenger': {
                'type': 'string'
            },
            'nonce': {
                '$#from': 'sequence',
                'type': 'string'
            },
            'settle_period_end': {
                '$#from': 'settlementPeriodEnd',
                'type': 'string'
            }
        }
    }
