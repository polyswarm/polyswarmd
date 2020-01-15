"""
This file has been automatically generated by scripts/gen_stubs.py
"""

from typing import Any, Dict, Generic, List, Mapping, Optional, TypeVar

try:
    from typing import TypedDict  # type: ignore
except ImportError:
    from mypy_extensions import TypedDict

D = TypeVar('D')
E = TypeVar('E')


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


class WebsocketEventMessage(Generic[D], Mapping):
    """An Polyswarm WebSocket message"""
    event: str
    data: D
    block_number: Optional[int]
    txhash: Optional[str]


TransferMessageData = TypedDict('TransferMessageData', {'to': str, 'from': str, 'value': str})

NewDepositMessageData = TypedDict('NewDepositMessageData', {'value': int, 'from': str})

NewWithdrawalMessageData = TypedDict('NewWithdrawalMessageData', {'to': str, 'value': int})

FeesUpdatedMessageData = TypedDict(
    'FeesUpdatedMessageData', {
        'bounty_fee': int,
        'assertion_fee': int
    }
)

WindowsUpdatedMessageData = TypedDict(
    'WindowsUpdatedMessageData', {
        'assertion_reveal_window': int,
        'arbiter_vote_window': int
    }
)

NewBountyMessageData = TypedDict(
    'NewBountyMessageData', {
        'guid': str,
        'artifact_type': str,
        'author': str,
        'amount': str,
        'uri': Any,
        'expiration': str,
        'metadata': str
    }
)

NewAssertionMessageData = TypedDict(
    'NewAssertionMessageData', {
        'bounty_guid': str,
        'author': str,
        'index': int,
        'bid': List[str],
        'mask': List[bool],
        'commitment': str
    }
)

RevealedAssertionMessageData = TypedDict(
    'RevealedAssertionMessageData', {
        'bounty_guid': str,
        'author': str,
        'index': int,
        'nonce': str,
        'verdicts': List[bool],
        'metadata': Any
    }
)

NewVoteMessageData = TypedDict(
    'NewVoteMessageData', {
        'bounty_guid': str,
        'voter': str,
        'votes': List[bool]
    }
)

QuorumReachedMessageData = TypedDict('QuorumReachedMessageData', {'bounty_guid': str})

SettledBountyMessageData = TypedDict(
    'SettledBountyMessageData', {
        'bounty_guid': str,
        'settler': str,
        'payout': int
    }
)

InitializedChannelMessageData = TypedDict(
    'InitializedChannelMessageData', {
        'ambassador': str,
        'expert': str,
        'guid': str,
        'multi_signature': str
    }
)

ClosedAgreementMessageData = TypedDict(
    'ClosedAgreementMessageData', {
        'ambassador': str,
        'expert': str
    }
)

StartedSettleMessageData = TypedDict(
    'StartedSettleMessageData', {
        'initiator': str,
        'nonce': int,
        'settle_period_end': int
    }
)

SettleStateChallengedMessageData = TypedDict(
    'SettleStateChallengedMessageData', {
        'challenger': str,
        'nonce': int,
        'settle_period_end': int
    }
)

DeprecatedMessageData = TypedDict('DeprecatedMessageData', {'rollover': bool})

UndeprecatedMessageData = TypedDict('UndeprecatedMessageData', {})

# Latest event's data type is not synthesized from a schema.
# If it's type changes, update gen_stubs.py
LatestEventMessageData = TypedDict('LatestEventMessageData', {'number': int})
