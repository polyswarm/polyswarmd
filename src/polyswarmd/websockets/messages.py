try:
    import ujson as json
except ImportError:
    import json

# from functools import lru_cache
from typing import List, Any

from polyswarmartifact import ArtifactType
# from polyswarmd.bounties import substitute_metadata
# from polyswarmd.config import Config
from polyswarmd.websockets.json_schema import copy_with_schema
# from requests_futures.sessions import FuturesSession

# session = FuturesSession(adapter_kwargs={'max_retries': 3})

# config = Config.auto()
# artifact_client = config['POLYSWARMD'].artifact_client
# redis_client = config['POLYSWARMD'].redis

Event = Any

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
        self.data = json.dumps({'event': self.event, 'data': data})

    def __str__(self):
        return self.data

    def __bytes__(self):
        return self.data.encode('ascii')


class WebsocketFilterMessage(WebsocketMessage):
    """Websocket message interface for etherem event entries. """
    _ws_event: str
    _ws_schema: str

    def __init__(self, event: Event):
        self.data = json.dump({
            'event': self.event_name,
            'data': self.extract(event),
            'block_number': event.blockNumber,
            'txhash': event.transactionHash.hex()
        })

    def str(self):
        return self.data

    @classmethod
    def extract(cls, source: Event):
        return copy_with_schema(cls._ws_schema, source)

    @classmethod
    def filter_event(cls) -> str:
        "The event name used by web3 (e.g 'Transfer' or 'FeesUpdated')"
        return str(cls.__name__)

    @property
    def event_name(self):
        return self._ws_event

    def __repr__(self):
        return f'<WebsocketFilterMessage name={self.event_name} filter_event={self.filter_event()}>'

# Methods for extracting information from an ethereum event log (suitable for websocket)
# @lru_cache(15)
# def _fetch_metadata(uri: str, validate, artifact_client=artifact_client, redis=redis_client):
#     return substitute_metadata(uri, artifact_client, session, validate, redis)

# def as_fetched_metadata(e: Event, k: str, *args):
#     return _fetch_metadata(e[k])

def as_fetched_metadata(e: Event, k: str, *args):
    return e[k]

def as_bv(e: Event, k: str, *args) -> List[bool]:
    "Return the bitvector for a number, where 1 is 'True' and 0 is 'False'"
    return [True if b == '1' else False for b in format(e[k], f"0>{e.numArtifacts}b")]

def as_artifact_type(e: Event, k: str, *args) -> str:
    return ArtifactType.to_string(ArtifactType(e.artifactType))

class Connected(WebsocketMessage):
    _ws_event = 'connected'

# Commonly used schema properties
bounty_guid = {'type': 'string', 'format': 'uuid', '$#from': 'bountyGuid'}

class FeesUpdated(WebsocketFilterMessage):
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


class WindowsUpdated(WebsocketFilterMessage):
    _ws_event = 'window_update'
    _ws_schema = {
        'properties': {
            'assertion_reveal_window': {
                'type': 'integer',
                '$#from': 'assertionRevealWindow'
            },
            'arbiter_vote_window': {
                'type': 'integer',
                '$#from': 'arbiterVoteWindow'
            }
        }
    }

class NewBounty(WebsocketFilterMessage):
    _ws_event = 'bounty'
    _ws_schema = {
        'properties': {
            'guid': {
                'type': 'string',
                'format': 'uuid',
            },
            'artifact_type': {
                'type': 'string',
                'enum': [ArtifactType.to_string(t) for t in ArtifactType],
                '$#convert': True,
                '$#fetch': as_artifact_type
            },
            'author': {
                'type': 'string',
                'format': 'ethaddr'
            },
            'amount': {
                'type': 'string',
                '$#convert': True,
            },
            'uri': {
                'type': 'string',
                '$#from': 'artifactURI'
            },
            'expiration': {
                '$#from': 'expirationBlock',
                '$#convert': True,
            },
            'metadata': {
                'type': 'object',
                '$#fetch': as_fetched_metadata
            }
        }
    }


class NewAssertion(WebsocketFilterMessage):
    _ws_event = 'assertion'
    _ws_schema = {
        'properties': {
            'bounty_guid': bounty_guid,
            'author': {
                'type': 'string',
                'format': 'ethaddr'
            },
            'index': {
                'type': 'integer'
            },
            'bid': {
                'type': 'array',
                'items': 'string',
                '$#convert': True,
            },
            'mask': {
                'type': 'array',
                'items': 'bool',
                '$#fetch': as_bv
            },
            'commitment': {
                'type': 'string',
                '$#convert': True,
            },
        },
    }


class RevealedAssertion(WebsocketFilterMessage):
    _ws_event = 'reveal'
    _ws_schema = {
        'properties': {
            'bounty_guid': bounty_guid,
            'author': {
                'type': 'string',
                'format': 'ethaddr'
            },
            'index': {
                'type': 'integer'
            },
            'nonce': {
                'type': 'string',
                '$#convert': True,
            },
            'verdicts': {
                'type': 'array',
                'items': 'boolean',
                '$#fetch': as_bv
            },
            'metadata': {
                'type': 'object',
                '$#fetch': as_fetched_metadata
            }
        }
    }


class NewVote(WebsocketFilterMessage):
    _ws_event = 'vote'
    _ws_schema = {
        'properties': {
            'bounty_guid': bounty_guid,
            'voter': {
                'type': 'string',
                'format': 'ethaddr'
            },
            'votes': {
                '$#fetch': as_bv,
                'items': 'bool',
                'type': 'array'
            }
        }
    }


class QuorumReached(WebsocketFilterMessage):
    _ws_event = 'quorum'
    _ws_schema = {
        'properties': {
            'bounty_guid': bounty_guid,
            'to': {
                'type': 'string',
                'format': 'ethaddr'
            },
            'from': {
                'type': 'string',
                'format': 'ethaddr'
            }
        }
    }


class SettledBounty(WebsocketFilterMessage):
    _ws_event = 'settled_bounty'
    _ws_schema = {
        'properties': {
            'bounty_guid': bounty_guid,
            'settler': {
                'type': 'integer',
                'format': 'ethaddr'
            },
            'payout': {
                'type': 'integer'
            }
        }
    }


class Deprecated(WebsocketFilterMessage):
    _ws_event = 'deprecated'


class InitializedChannel(WebsocketFilterMessage):
    _ws_event = 'initialized_channel'
    _ws_schema = {
        'properties': {
            'ambassador': {
                'type': 'string',
                'format': 'ethaddr'
            },
            'expert': {
                'type': 'string',
                'format': 'ethaddr'
            },
            'guid': {
                'type': 'string',
                'format': 'uuid',
            },
            'multi_signature': {
                '$#from': 'msig',
                'type': 'string',
                'format': 'ethaddr',
            }
        }
    }


class LatestEvent(WebsocketFilterMessage):
    _ws_event = 'block'
    _chain = None

    def __init__(self, event):
        self.data = json.dumps({
            'event': self.event_name,
            'data': {
                'number': self.block_number
            }
        })

    @classmethod
    def filter_event(cls):
        return 'latest'

    @property
    def block_number(self):
        return self._chain.blockNumber

    @classmethod
    def make(cls, chain):
        cls._chain = chain
        return cls


class ClosedAgreement(WebsocketFilterMessage):
    _ws_event = 'closed_agreement'
    _ws_schema = {
        'properties': {
            'ambassador': {
                '$#from': '_ambassador',
                'type': 'string',
                'format': 'ethaddr',
            },
            'expert': {
                '$#from': '_expert',
                'type': 'string',
                'format': 'ethaddr',
            }
        }
    }


class StartedSettle(WebsocketFilterMessage):
    _ws_event = 'settle_started'
    _ws_schema = {
        'properties': {
            'initiator': {
                'type': 'string',
                'format': 'ethaddr'
            },
            'nonce': {
                '$#from': 'sequence',
                'type': 'integer'
            },
            'settle_period_end': {
                '$#from': 'settlementPeriodEnd',
                'type': 'integer'
            }
        }
    }


class SettleStateChallenged(WebsocketFilterMessage):
    _ws_event = 'settle_challenged'
    _ws_schema = {
        'properties': {
            'challenger': {
                'type': 'string',
                'format': 'ethaddr'
            },
            'nonce': {
                '$#from': 'sequence',
                'type': 'integer'
            },
            'settle_period_end': {
                '$#from': 'settlementPeriodEnd',
                'type': 'integer'
            }
        }
    }
