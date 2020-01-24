import uuid

from hexbytes import HexBytes
import pytest

import polyswarmd.utils
from polyswarmd.websockets.messages import (
    ClosedAgreement,
    Deprecated,
    FeesUpdated,
    InitializedChannel,
    LatestEvent,
    NewAssertion,
    NewBounty,
    NewDeposit,
    NewVote,
    NewWithdrawal,
    OpenedAgreement,
    QuorumReached,
    RevealedAssertion,
    SettledBounty,
    SettleStateChallenged,
    StartedSettle,
    Transfer,
    Undeprecated,
    WindowsUpdated,
)

ws_event = 'NOP'
log_index = 19845
transaction_index = 1276
txhash_b = HexBytes(11)
txhash_bv = txhash_b.hex()
block_hash = HexBytes(90909090)
block_hash_v = block_hash.hex()
ethaddr_1 = "0x4F10166CaFD7856ea946124927D4478fDD18d979"
ethaddr_2 = "0x34E583cf9C1789c3141538EeC77D9F0B8F7E89f2"
bounty_fee = 500000000001
assertion_fee = 500000000002
transfer_receipt = {'to': ethaddr_1, 'from': ethaddr_2, 'value': 1}
nonce = 1752
reveal_metadata = {
    'malware_family': 'EICAR',
    'scanner': {
        'environment': {
            'architecture': 'x86_64',
            'operating_system': 'Linux',
        }
    }
}
bounty_metadata = {
    "md5": "44d88612fea8a8f36de82e1278abb02f",
    "sha1": "3395856ce81f2b7382dee72602f798b642f14140",
    "size": 68,
    "type": "FILE",
    "sha256": "275a021bbfb6489e54d471899f7db9d1663fc695ec2fe2a2c4538aabf651fd0f",
    "filename": "eicar_true",
    "mimetype": "text/plain",
    "bounty_id": 69540800813340,
    "extended_type": "EICAR virus test files",
}

bounty_artifact_uri = 'http://s3.amazon.com/s3/bounty_uri'
reveal_artifact_uri = 'http://s3.amazon.com/s3/reveal_uri'

arbiter_addr = "0xF870491ea0F53F67846Eecb57855284D8270284D"
ambassador = "0xF2E246BB76DF876Cef8b38ae84130F4F55De395b"
expert_addr = "0xDF9246BB76DF876Cef8bf8af8493074755feb58c"
multisig_addr = "0x789246BB76D18C6C7f8bd8ac8423478795f71bf9"

bx = 128
num_artifacts = 7
bx_to_boollist = polyswarmd.utils.safe_int_to_bool_list(bx, num_artifacts)

guidint = 16577
guidstr = str(uuid.UUID(int=guidint))

bguidint = 751207
bguidstr = str(uuid.UUID(int=bguidint))

serializations = [
    (
        ClosedAgreement,
        {
            '_ambassador': ambassador,
            '_expert': expert_addr,
        },
        {
            'ambassador': ambassador,
            'expert': expert_addr,
        },
        'closed_agreement',
    ),
    (
        Deprecated,
        {
            'rollover': True
        },
        {
            'rollover': True,
        },
        'deprecated',
    ),
    (
        FeesUpdated,
        {
            'bountyFee': bounty_fee,
            'assertionFee': assertion_fee,
        },
        {
            'bounty_fee': bounty_fee,
            'assertion_fee': assertion_fee,
        },
        'fee_update',
    ),
    (
        InitializedChannel,
        {
            'ambassador': ambassador,
            'expert': expert_addr,
            'guid': guidint,
            'msig': multisig_addr,
        },
        {
            'ambassador': ambassador,
            'expert': expert_addr,
            'guid': guidstr,
            'multi_signature': multisig_addr,
        },
        'initialized_channel',
    ),
    (
        NewAssertion,
        {
            'bountyGuid': bguidint,
            'author': ambassador,
            'index': 1,
            'bid': [1, 2, 3],
            'mask': bx,
            'commitment': 100,
            'numArtifacts': num_artifacts,
        },
        {
            'author': ambassador,
            'bid': ['1', '2', '3'],
            'bounty_guid': bguidstr,
            'commitment': '100',
            'index': 1,
            'mask': bx_to_boollist,
        },
        'assertion',
    ),
    (
        NewBounty,
        {
            'guid': guidint,
            'artifactType': 1,
            'author': ethaddr_1,
            'amount': 10,
            'artifactURI': bounty_artifact_uri,
            'expirationBlock': 118,
            'metadata': bounty_artifact_uri,
        },
        {
            'amount': '10',
            'artifact_type': 'url',
            'author': ethaddr_1,
            'expiration': '118',
            'guid': guidstr,
            'metadata': [bounty_metadata],
            'uri': bounty_artifact_uri,
        },
        'bounty',
    ),
    (
        (NewBounty, 'NewBounty_no_metadata'),
        {
            'guid': guidint,
            'artifactType': 1,
            'author': ethaddr_1,
            'amount': 10,
            'artifactURI': bounty_artifact_uri,
            'expirationBlock': 118,
            'metadata': None,
        },
        {
            'amount': '10',
            'artifact_type': 'url',
            'author': ethaddr_1,
            'expiration': '118',
            'guid': guidstr,
            'metadata': None,
            'uri': bounty_artifact_uri,
        },
        'bounty',
    ),
    (
        NewVote,
        {
            'bountyGuid': bguidint,
            'voter': expert_addr,
            'votes': bx,
            'numArtifacts': num_artifacts,
        },
        {
            'bounty_guid': bguidstr,
            'voter': expert_addr,
            'votes': bx_to_boollist,
        },
        'vote',
    ),
    (
        QuorumReached,
        {
            'bountyGuid': bguidint,
        },
        {
            'bounty_guid': bguidstr,
        },
        'quorum',
    ),
    (
        RevealedAssertion,
        {
            'bountyGuid': bguidint,
            'author': expert_addr,
            'index': 10,
            'verdicts': bx,
            'nonce': nonce,
            'numArtifacts': num_artifacts,
            'artifactURI': reveal_artifact_uri,
            'metadata': reveal_artifact_uri,
        },
        {
            'author': expert_addr,
            'bounty_guid': bguidstr,
            'index': 10,
            'metadata': [reveal_metadata],
            'nonce': str(nonce),
            'verdicts': bx_to_boollist,
        },
        'reveal',
    ),
    (
        SettleStateChallenged,
        {
            'challenger': ethaddr_1,
            'sequence': nonce,
            'settlementPeriodEnd': 229,
        },
        {
            'challenger': ethaddr_1,
            'nonce': nonce,
            'settle_period_end': 229,
        },
        'settle_challenged',
    ),
    (
        SettledBounty,
        {
            'bountyGuid': bguidint,
            'settler': ethaddr_1,
            'payout': 1000,
        },
        {
            'bounty_guid': bguidstr,
            'payout': 1000,
            'settler': ethaddr_1,
        },
        'settled_bounty',
    ),
    (
        StartedSettle,
        {
            'initiator': ethaddr_1,
            'sequence': nonce,
            'settlementPeriodEnd': 229,
        },
        {
            'initiator': ethaddr_1,
            'nonce': nonce,
            'settle_period_end': 229,
        },
        'settle_started',
    ),
    (
        Undeprecated,
        {
            'a': 1,
            'hello': 'world',
            'should_not_show_up': True
        },
        {},
        'undeprecated',
    ),
    (
        WindowsUpdated,
        {
            'assertionRevealWindow': 100,
            'arbiterVoteWindow': 105,
        },
        {
            'arbiter_vote_window': 105,
            'assertion_reveal_window': 100,
        },
        'window_update',
    ),
    (NewDeposit, transfer_receipt, {
        'value': 1,
        'from': ethaddr_2
    }),
    (NewWithdrawal, transfer_receipt, {
        'value': 1,
        'to': ethaddr_1
    }),
    (OpenedAgreement, transfer_receipt, {
        'value': 1,
        'from': ethaddr_2,
        'to': ethaddr_1,
    }),
    (Transfer, transfer_receipt, {
        'value': str(1),
        'from': ethaddr_2,
        'to': ethaddr_1,
    }),
]
