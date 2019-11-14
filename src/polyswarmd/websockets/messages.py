try:
    import ujson as json
except ImportError:
    import json

from functools import lru_cache
from typing import List

from polyswarmartifact import ArtifactType
from polyswarm.json_schema import JSONSchema, copy_with_schema
from polyswarmd import app
from polyswarmd.bounties import substitute_metadata
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


class WebsocketEventlogMessage(WebsocketMessage):
    """Websocket message interface for etherem event entries. """

    _ws_event: str
    _ws_schema: JSONSchema

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

    @property
    def filter_event(self) -> str:
        "The event name used by web3 (e.g 'Transfer' or 'FeesUpdated')"
        return self.__class__.__name__

    @property
    def event_name(self):
        return self._ws_event

    def __repr__(self):
        return f'<WebsocketEventlogMessage name={self.event_name} filter_event={self.filter_event}>'


session = FuturesSession(adapter_kwargs={'max_retries': 3})
artifact_client = app.config['POLYSWARMD'].artifact_client
redis_client = app.config['POLYSWARMD'].redis

@lru_cache(15)
def _fetch_metadata(uri: str, validate, artifact_client=artifact_client, redis=redis_client):
    return substitute_metadata(uri, artifact_client, session, validate, redis)

def as_fetched_metadata(e: Event, k: str, *args):
    return _fetch_metadata(e[k])

def as_bv(e: Event, k: str, *args) -> List[bool]:
    "Return the bitvector for a number, where 1 is 'True' and 0 is 'False'"
    return [True if b == '1' else False for b in format(e[k], f"0>{e.numArtifacts}b")]

def as_artifact_type(e: Event, k: str, *args) -> str:
    return ArtifactType.to_string(ArtifactType(e.artifactType))

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
                '$#from': 'assertionRevealWindow'
            },
            'arbiter_vote_window': {
                'type': 'integer',
                '$#from': 'arbiterVoteWindow'
            }
        }
    }


class NewBounty(WebsocketEventlogMessage):
    _ws_event = 'bounty'
    _ws_schema = {
        'properties': {
            'guid': {
                'type': 'string',
                'format': 'uuid',
            },
            'artifact_type': {
                'type': 'string',
                'enum': [ArtifactType.to_string(t.value) for t in ArtifactType],
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


class NewAssertion(WebsocketEventlogMessage):
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


class RevealedAssertion(WebsocketEventlogMessage):
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


class NewVote(WebsocketEventlogMessage):
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


class QuorumReached(WebsocketEventlogMessage):
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


class SettledBounty(WebsocketEventlogMessage):
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


class Deprecated(WebsocketEventlogMessage):
    _ws_event = 'deprecated'


class InitializedChannel(WebsocketEventlogMessage):
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


class StartedSettle(WebsocketEventlogMessage):
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


class SettleStateChallenged(WebsocketEventlogMessage):
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
