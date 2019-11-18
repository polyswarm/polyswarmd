try:
    import ujson as json
except ImportError:
    import json
from abc import ABC
from typing import Any

from polyswarmartifact import ArtifactType

from .json_schema import copy_with_schema


class WebsocketMessage():
    "Represent a message that can be handled by polyswarm-client"
    # This is the identifier used when building a websocket event identifier.
    _ws_event: str
    __slots__ = ('data')

    def __init__(self, data={}):
        if not self._ws_event:
            raise ValueError("This class has no websocket event name")
        self.data = json.dumps({'event': self.ws_event, 'data': data})

    @property
    def ws_event(self) -> str:
        return self._ws_event

    def __str__(self):
        return self.data

    def __bytes__(self):
        return self.data.encode('ascii')


class Connected(WebsocketMessage):
    _ws_event = 'connected'


EventLogEntry = Any


class EventLogMessage(ABC):
    _extraction_schema: str

    @classmethod
    def extract(cls, source: EventLogEntry):
        "Extract the fields indicated in _extraction_schema from the event log message"
        return copy_with_schema(cls._extraction_schema, source)

    @classmethod
    def contract_event_name(cls) -> str:
        "The event name used by web3 (e.g 'Transfer' or 'FeesUpdated')"
        return str(cls.__name__)

    def __repr__(self):
        return f'<EventLogMessage contract_event_name={self.contract_event_name()}>'


# Commonly used schema properties
uint256 = {'type': 'integer'}
guid = {'type': 'string', 'format': 'uuid'}
bounty_guid = {**guid, '$#from': 'bountyGuid'}
ethereum_address = {'type': 'string', 'format': 'ethaddr'}

# The fetch routine uses format to split into a bitvector, e.g format(16, "0>10b") => '0000010000'
boolvector = {
    'type': 'array',
    'items': 'boolean',
    '$#fetch': lambda e, k, *args: [b != '0' for b in format(int(e[k]), f"0>{e.numArtifacts}b")]
}

## The functions below are commented out because they depend on configuration being loaded from PolyswarmD.
# from functools import lru_cache
# from polyswarmd.bounties import substitute_metadata
# from requests_futures.sessions import FuturesSession
# session = FuturesSession(adapter_kwargs={'max_retries': 3})
# from polyswarmd.config import Config
# config = Config.auto()
# artifact_client = config['POLYSWARMD'].artifact_client
# redis_client = config['POLYSWARMD'].redis
# Methods for extracting information from an ethereum event log (suitable for websocket)
# @lru_cache(15)
# def _fetch_metadata(uri: str, validate=None, artifact_client=artifact_client, redis=redis):
#     raise NotImplementedError("This function relies on config information in PolyswarmD")
#     return substitute_metadata(uri, artifact_client, session, validate, redis)
# artifact_metadata = {'type': 'object', '$#fetch': lambda e, k, *args: _fetch_metadata(e[k]) }

artifact_metadata = {'type': 'object', '$#fetch': lambda e, k, *args: e[k]}


class Transfer(EventLogMessage):
    _extraction_schema = {
        'properties': {
            'to': ethereum_address,
            'from': ethereum_address,
            'value': {
                'type': 'string'
            }
        }
    }


class NewWithdrawal(EventLogMessage):
    _extraction_schema = {
        'properties': {
            'to': ethereum_address,
            'from': ethereum_address,
        }
    }


class NewDeposit(EventLogMessage):
    _extraction_schema = {
        'properties': {
            'to': ethereum_address,
            'from': ethereum_address,
        }
    }


# The classes below have no defined extraction ('conversion') logic,
# so they simply return the argument to `extract` as a `dict`
extract_all = {'extract': property(lambda self, event: dict(event))}

OpenedAgreement = type('OpenedAgreement', (EventLogMessage, ), extract_all)
CanceledAgreement = type('CanceledAgreement', (EventLogMessage, ), extract_all)
JoinedAgreement = type('JoinedAgreement', (EventLogMessage, ), extract_all)
ClosedAgreement = type('ClosedAgreement', (EventLogMessage, ), extract_all)
StartedSettle = type('StartedSettle', (EventLogMessage, ), extract_all)


class WebsocketFilterMessage(WebsocketMessage, EventLogMessage):
    """Websocket message interface for etherem event entries. """
    _ws_event: str
    _extraction_schema: dict

    def __init__(self, event: EventLogEntry):
        self.data = json.dumps({
            'event': self.ws_event,
            'data': self.extract(event),
            'block_number': event.blockNumber,
            'txhash': event.transactionHash.hex()
        })

    def __repr__(self):
        return f'<WebsocketFilterMessage name={self.ws_event} contract_event_name={self.contract_event_name()}>'


class FeesUpdated(WebsocketFilterMessage):
    _ws_event = 'fee_update'
    _extraction_schema = {
        'properties': {
            'bounty_fee': {
                **uint256, '$#from': 'bountyFee'
            },
            'assertion_fee': {
                **uint256, '$#from': 'assertionFee'
            }
        },
    }


class WindowsUpdated(WebsocketFilterMessage):
    _ws_event = 'window_update'
    _extraction_schema = {
        'properties': {
            'assertion_reveal_window': {
                **uint256, '$#from': 'assertionRevealWindow'
            },
            'arbiter_vote_window': {
                **uint256, '$#from': 'arbiterVoteWindow'
            }
        }
    }


class NewBounty(WebsocketFilterMessage):
    _ws_event = 'bounty'
    _extraction_schema = {
        'properties': {
            'guid': guid,
            'artifact_type': {
                'type': 'string',
                'enum': [ArtifactType.to_string(t) for t in ArtifactType],
                '$#convert': True,
                '$#fetch': lambda e, k, *args: ArtifactType.to_string(ArtifactType(e.artifactType))
            },
            'author': ethereum_address,
            'amount': {
                '$#convert': True,
                'type': 'string',
            },
            'uri': {
                'type': 'string',
                '$#from': 'artifactURI'
            },
            'expiration': {
                '$#from': 'expirationBlock',
                'type': 'string',
                '$#convert': True,
            },
            'metadata': artifact_metadata
        }
    }


class NewAssertion(WebsocketFilterMessage):
    _ws_event = 'assertion'
    _extraction_schema = {
        'properties': {
            'bounty_guid': bounty_guid,
            'author': ethereum_address,
            'index': uint256,
            'bid': {
                'type': 'array',
                'items': 'string',
                '$#convert': True,
            },
            'mask': boolvector,
            'commitment': {
                'type': 'string',
                '$#convert': True,
            },
        },
    }


class RevealedAssertion(WebsocketFilterMessage):
    _ws_event = 'reveal'
    _extraction_schema = {
        'properties': {
            'bounty_guid': bounty_guid,
            'author': ethereum_address,
            'index': uint256,
            'nonce': {
                'type': 'string',
                '$#convert': True,
            },
            'verdicts': boolvector,
            'metadata': artifact_metadata
        }
    }


class NewVote(WebsocketFilterMessage):
    _ws_event = 'vote'
    _extraction_schema = {'properties': {'bounty_guid': bounty_guid, 'voter': ethereum_address, 'votes': boolvector}}


class QuorumReached(WebsocketFilterMessage):
    _ws_event = 'quorum'
    _extraction_schema = {
        'properties': {
            'bounty_guid': bounty_guid,
            'to': ethereum_address,
            'from': ethereum_address,
        }
    }


class SettledBounty(WebsocketFilterMessage):
    _ws_event = 'settled_bounty'
    _extraction_schema = {'properties': {'bounty_guid': bounty_guid, 'settler': ethereum_address, 'payout': uint256}}


class InitializedChannel(WebsocketFilterMessage):
    _ws_event = 'initialized_channel'
    _extraction_schema = {
        'properties': {
            'ambassador': ethereum_address,
            'expert': ethereum_address,
            'guid': guid,
            'multi_signature': {
                '$#from': 'msig',
                **ethereum_address
            }
        }
    }


class ClosedAgreement(WebsocketFilterMessage):
    _ws_event = 'closed_agreement'
    _extraction_schema = {
        'properties': {
            'ambassador': {
                '$#from': '_ambassador',
                **ethereum_address
            },
            'expert': {
                '$#from': '_expert',
                **ethereum_address
            }
        }
    }


class StartedSettle(WebsocketFilterMessage):
    _ws_event = 'settle_started'
    _extraction_schema = {
        'properties': {
            'initiator': ethereum_address,
            'nonce': {
                '$#from': 'sequence',
                **uint256
            },
            'settle_period_end': {
                '$#from': 'settlementPeriodEnd',
                **uint256
            }
        }
    }


class SettleStateChallenged(WebsocketFilterMessage):
    _ws_event = 'settle_challenged'
    _extraction_schema = {
        'properties': {
            'challenger': ethereum_address,
            'nonce': {
                '$#from': 'sequence',
                **uint256
            },
            'settle_period_end': {
                '$#from': 'settlementPeriodEnd',
                **uint256
            }
        }
    }


class Deprecated(WebsocketFilterMessage):
    _ws_event = 'deprecated'


class LatestEvent(WebsocketFilterMessage):
    _ws_event = 'block'
    _chain = None

    def __init__(self, event):
        self.data = json.dumps({'event': self.ws_event, 'data': {'number': self.block_number}})

    @classmethod
    def contract_event_name(cls):
        return 'latest'

    @property
    def block_number(self):
        if self._chain:
            return self._chain.blockNumber
        else:
            return -1

    @classmethod
    def make(cls, chain):
        cls._chain = chain
        return cls
