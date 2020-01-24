from hexbytes import HexBytes
import pytest

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
addr1 = "0x0000000000000000000000000000000000000001"
addr2 = "0x0000000000000000000000000000000000000002"
bounty_fee = 500000000001
assertion_fee = 500000000002
transfer_receipt = {'to': addr1, 'from': addr2, 'value': 1}
nonce = 1752
bounty_metadata = {
    'malware_family': 'EICAR',
    'scanner': {
        'environment': {
            'architecture': 'x86_64',
            'operating_system': 'Linux',
        }
    }
}
assertion_metadata = {
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
assertion_artifact_uri = 'http://s3.amazon.com/s3/assertion_uri'

ambassador = "0xF2E246BB76DF876Cef8b38ae84130F4F55De395b"
expert_addr = "0xDF9246BB76DF876Cef8bf8af8493074755feb58c"
multisig_addr = "0x789246BB76D18C6C7f8bd8ac8423478795f71bf9"

_msg_fixtures = [
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
            'guid': 1,
            'msig': multisig_addr,
        },
        {
            'ambassador': ambassador,
            'expert': expert_addr,
            'guid': '00000000-0000-0000-0000-000000000001',
            'multi_signature': multisig_addr,
        },
        'initialized_channel',
    ),
    (
        NewAssertion,
        {
            'bountyGuid': 1,
            'author': ambassador,
            'index': 1,
            'bid': [1, 2, 3],
            'mask': 32,
            'commitment': 100,
            'numArtifacts': 4,
        },
        {
            'author': ambassador,
            'bid': ['1', '2', '3'],
            'bounty_guid': '00000000-0000-0000-0000-000000000001',
            'commitment': '100',
            'index': 1,
            'mask': [False, False, False, False, False, True],
        },
        'assertion',
    ),
    (
        NewBounty,
        {
            'guid': 1066,
            'artifactType': 1,
            'author': addr1,
            'amount': 10,
            'artifactURI': assertion_artifact_uri,
            'expirationBlock': 118,
            'metadata': '',
        },
        {
            'amount': '10',
            'artifact_type': 'url',
            'author': addr1,
            'expiration': '118',
            'guid': '00000000-0000-0000-0000-00000000042a',
            'metadata': [assertion_metadata],
            'uri': assertion_artifact_uri,
        },
        'bounty',
    ),
    (
        NewVote,
        {
            'bountyGuid': 2,
            'voter': expert_addr,
            'votes': 128,
            'numArtifacts': 4,
        },
        {
            'bounty_guid': '00000000-0000-0000-0000-000000000002',
            'voter': expert_addr,
            'votes': [False, False, False, False, False, False, False, True],
        },
        'vote',
    ),
    (
        QuorumReached,
        {
            'bountyGuid': 16577,
        },
        {
            'bounty_guid': '00000000-0000-0000-0000-0000000040c1',
        },
        'quorum',
    ),
    (
        RevealedAssertion,
        {
            'bountyGuid': 2,
            'author': expert_addr,
            'index': 10,
            'verdicts': 128,
            'nonce': nonce,
            'numArtifacts': 4,
            'artifactURI': bounty_artifact_uri,
            'metadata': '',
        },
        {
            'author': expert_addr,
            'bounty_guid': '00000000-0000-0000-0000-000000000002',
            'index': 10,
            'metadata': [bounty_metadata],
            'nonce': str(nonce),
            'verdicts': [False, False, False, False, False, False, False, True],
        },
        'reveal',
    ),
    (
        SettleStateChallenged,
        {
            'challenger': addr1,
            'sequence': nonce,
            'settlementPeriodEnd': 229,
        },
        {
            'challenger': addr1,
            'nonce': nonce,
            'settle_period_end': 229,
        },
        'settle_challenged',
    ),
    (
        SettledBounty,
        {
            'bountyGuid': 16577,
            'settler': addr1,
            'payout': 1000,
        },
        {
            'bounty_guid': '00000000-0000-0000-0000-0000000040c1',
            'payout': 1000,
            'settler': addr1,
        },
        'settled_bounty',
    ),
    (
        StartedSettle,
        {
            'initiator': addr1,
            'sequence': nonce,
            'settlementPeriodEnd': 229,
        },
        {
            'initiator': addr1,
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
        'from': addr2
    }),
    (NewWithdrawal, transfer_receipt, {
        'value': 1,
        'to': addr1
    }),
    (OpenedAgreement, transfer_receipt, {
        'value': 1,
        'from': addr2,
        'to': addr1,
    }),
    (Transfer, transfer_receipt, {
        'value': str(1),
        'from': addr2,
        'to': addr1,
    }),
]

expected_contract_event_messages = [
    pytest.param(f, id=f[0].__name__) for f in _msg_fixtures if len(f) > 3
]
expected_extractions = [pytest.param(f, id=f[0].__name__) for f in _msg_fixtures]
