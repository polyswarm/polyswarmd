"""
NOTE: These tests were automatically translated and are therefore a bit wonky.

Feel free to make it better
"""
from collections import UserDict, namedtuple
import json
from pprint import pprint

from hexbytes import HexBytes
import pytest
import ujson

from polyswarmd.websockets import types
from polyswarmd.websockets.messages import (
    ClosedAgreement,
    ContractEvent,
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
    WebsocketMessage,
    WindowsUpdated,
)

TestChain = namedtuple('TestChain', ['blockNumber'])
FakeFormatter = namedtuple('FakeFormatter', ['contract_event_name'])


@pytest.fixture
def ws_event():
    return 'NOP'


@pytest.fixture
def log_index():
    return 19845


@pytest.fixture
def transactionIndex():
    1276


@pytest.fixture
def txhash_b():
    return HexBytes(11).to_bytes(32, byteorder='big')


@pytest.fixture
def block_hash():
    return (90909090).to_bytes(32, byteorder='big')


@pytest.fixture
def mkevent(block_number, transaction_index, txhash_b, token_address, block_hash):

    class MKEvent(UserDict):
        DEFAULT_BLOCK = block_number
        ALTERNATE_BLOCK = 220

        def __init__(self, *args, **kwargs):
            event_default = {
                'args': {},
                'event': ws_event,
                'logIndex': log_index,
                'transactionIndex': transaction_index,
                'transactionHash': txhash_b,
                'address': token_address,
                'blockHash': block_hash,
                'blockNumber': block_number,
            }
            for i, (attr, default) in enumerate(event_default.items()):
                if len(args) > i:
                    event_default[attr] = args[i]
            event_default.update(kwargs)
            self.data = event_default

        def __getattr__(self, k):
            if (type(k) == str):
                return self.data[k]

    return MKEvent


@pytest.fixture
def decoded_msg():
    return lambda wsmsg: pprint(json.loads(wsmsg.decode('ascii')))


@pytest.fixture(autouse=True)
def mock_md_fetch(monkeypatch):
    """Mock out the metadata-fetching implementation

    Override _substitute_metadata so we can test `fetch_metadata' without network IO.
    doctest.testmod does accept globals-setting parameters (`globs` & `extraglobs'), but they
    haven't been as easy as just overwriting messages here
    """

    def mock_sub(cls, uri):
        # These are fake URIs, intended to resemble the output that substitute_metadata might
        # actually encounter.
        fake_uris = {
            'ZWbountyuri':
                ujson.dumps([{
                    "malware_family": "EICAR",
                    "scanner": {
                        "environment": {
                            "architecture": "x86_64",
                            "operating_system": "Linux"
                        }
                    }
                }]),
            'ZWassertionuri':
                ujson.dumps([{
                    "md5": "44d88612fea8a8f36de82e1278abb02f",
                    "sha1": "3395856ce81f2b7382dee72602f798b642f14140",
                    "size": 68,
                    "type": "FILE",
                    "sha256": "275a021bbfb6489e54d471899f7db9d1663fc695ec2fe2a2c4538aabf651fd0f",
                    "filename": "eicar_true",
                    "mimetype": "text/plain",
                    "bounty_id": 69540800813340,
                    "extended_type": "EICAR virus test files",
                }])
        }
        if uri in fake_uris:
            content = json.loads(fake_uris[uri])

        if cls._metadata_validator:
            if cls._metadata_validator(content):
                return content
            else:
                return None
        return uri

    monkeypatch.setattr(types.ArtifactMetadata, "substitute", mock_sub)


def test_messages_ClosedAgreement(mkevent, decoded_msg, txhash_b, block_number):
    event = mkevent({
        '_ambassador': '0xF2E246BB76DF876Cef8b38ae84130F4F55De395b',
        '_expert': '0xDF9246BB76DF876Cef8bf8af8493074755feb58c',
    })
    assert decoded_msg(ClosedAgreement.serialize_message(event)) == {
        'block_number': block_number,
        'data': {
            'ambassador': '0xF2E246BB76DF876Cef8b38ae84130F4F55De395b',
            'expert': '0xDF9246BB76DF876Cef8bf8af8493074755feb58c'
        },
        'event': 'closed_agreement',
        'txhash': txhash_b,
    }


def test_messages_Deprecated(mkevent, decoded_msg, txhash_b, block_number):
    event = mkevent({'rollover': True})
    assert Deprecated.contract_event_name == 'Deprecated'
    assert decoded_msg(Deprecated.serialize_message(event)) == {
        'block_number': block_number,
        'data': {
            'rollover': True
        },
        'event': 'deprecated',
        'txhash': txhash_b,
    }


def test_messages_FeesUpdated(mkevent, decoded_msg, txhash_b, block_number):
    event = mkevent({'bountyFee': 5000000000000000, 'assertionFee': 5000000000000000})
    assert decoded_msg(FeesUpdated.serialize_message(event)) == {
        'block_number': block_number,
        'data': {
            'assertion_fee': 5000000000000000,
            'bounty_fee': 5000000000000000
        },
        'event': 'fee_update',
        'txhash': txhash_b,
    }

    assert FeesUpdated.contract_event_name == 'FeesUpdated'


def test_messages_InitializedChannel(mkevent, decoded_msg, txhash_b, block_number):

    event = mkevent({
        'ambassador': '0xF2E246BB76DF876Cef8b38ae84130F4F55De395b',
        'expert': '0xDF9246BB76DF876Cef8bf8af8493074755feb58c',
        'guid': 1,
        'msig': '0x789246BB76D18C6C7f8bd8ac8423478795f71bf9'
    })

    assert decoded_msg(InitializedChannel.serialize_message(event)) == {
        'block_number': block_number,
        'data': {
            'ambassador': '0xF2E246BB76DF876Cef8b38ae84130F4F55De395b',
            'expert': '0xDF9246BB76DF876Cef8bf8af8493074755feb58c',
            'guid': '00000000-0000-0000-0000-000000000001',
            'multi_signature': '0x789246BB76D18C6C7f8bd8ac8423478795f71bf9'
        },
        'event': 'initialized_channel',
        'txhash': txhash_b,
    }


def test_messages_LatestEvent(mkevent, decoded_msg, block_number):
    LE = LatestEvent.make(TestChain(block_number))
    LA = LatestEvent.make(TestChain(block_number + 1))
    event = mkevent({'a': 1, 'hello': 'world', 'should_not_be_here': True})
    assert LE.contract_event_name == 'latest'
    assert LA.contract_event_name == 'latest'
    assert decoded_msg(LE.serialize_message(event)) == {
        'data': {
            'number': block_number
        },
        'event': 'block'
    }

    assert decoded_msg(LA.serialize_message(event)) == {
        'data': {
            'number': block_number + 1
        },
        'event': 'block'
    }


def test_messages_NewAssertion(mkevent, decoded_msg, txhash_b, block_number):

    event = mkevent({
        'bountyGuid': 1,
        'author': '0xF2E246BB76DF876Cef8b38ae84130F4F55De395b',
        'index': 1,
        'bid': [1, 2, 3],
        'mask': 32,
        'commitment': 100,
        'numArtifacts': 4
    })

    assert decoded_msg(NewAssertion.serialize_message(event)) == {
        'block_number': block_number,
        'data': {
            'author': '0xF2E246BB76DF876Cef8b38ae84130F4F55De395b',
            'bid': ['1', '2', '3'],
            'bounty_guid': '00000000-0000-0000-0000-000000000001',
            'commitment': '100',
            'index': 1,
            'mask': [False, False, False, False, False, True]
        },
        'event': 'assertion',
        'txhash': txhash_b,
    }


def test_messages_NewBounty(mkevent, decoded_msg, addr1, txhash_b, block_number):

    event = mkevent({
        'guid': 1066,
        'artifactType': 1,
        'author': addr1,
        'amount': 10,
        'artifactURI': '912bnadf01295',
        'expirationBlock': 118,
        'metadata': 'ZWassertionuri'
    })

    assert decoded_msg(NewBounty.serialize_message(event)) == {
        'block_number': block_number,
        'data': {
            'amount': '10',
            'artifact_type': 'url',
            'author': '0x0000000000000000000000000000000000000001',
            'expiration': '118',
            'guid': '00000000-0000-0000-0000-00000000042a',
            'metadata': [{
                'bounty_id': 69540800813340,
                'extended_type': 'EICAR virus test files',
                'filename': 'eicar_true',
                'md5': '44d88612fea8a8f36de82e1278abb02f',
                'mimetype': 'text/plain',
                'sha1': '3395856ce81f2b7382dee72602f798b642f14140',
                'sha256': '275a021bbfb6489e54d471899f7db9d1663fc695ec2fe2a2c4538aabf651fd0f',
                'size': 68,
                'type': 'FILE'
            }],
            'uri': '912bnadf01295'
        },
        'event': 'bounty',
        'txhash': txhash_b,
    }


def test_messages_NewDeposit(mkevent, decoded_msg, addr2):

    assert NewDeposit.extract({
        'from': addr2,
        'value': 1
    }) == {
        'value': 1,
        'from': '0x0000000000000000000000000000000000000002'
    }

    assert NewDeposit.contract_event_name == 'NewDeposit'


def test_messages_NewVote(mkevent, decoded_msg, txhash_b, block_number):

    event = mkevent({
        'bountyGuid': 2,
        'voter': '0xDF9246BB76DF876Cef8bf8af8493074755feb58c',
        'votes': 128,
        'numArtifacts': 4
    })

    assert decoded_msg(NewVote.serialize_message(event)) == {
        'block_number': block_number,
        'data': {
            'bounty_guid': '00000000-0000-0000-0000-000000000002',
            'voter': '0xDF9246BB76DF876Cef8bf8af8493074755feb58c',
            'votes': [False, False, False, False, False, False, False, True]
        },
        'event': 'vote',
        'txhash': txhash_b,
    }


def test_messages_NewWithdrawal(mkevent, decoded_msg, addr1, addr2):
    assert NewWithdrawal.extract({
        'to': addr1,
        'from': addr2,
        'value': 1
    }) == {
        'to': '0x0000000000000000000000000000000000000001',
        'value': 1
    }
    assert NewWithdrawal.contract_event_name == 'NewWithdrawal'


def test_messages_OpenedAgreement(mkevent, decoded_msg, addr1, addr2, pprint):
    assert pprint(OpenedAgreement.extract({
        'to': addr1,
        'from': addr2,
        'value': 1
    })) == {
        'from': '0x0000000000000000000000000000000000000002',
        'to': '0x0000000000000000000000000000000000000001',
        'value': 1
    }

    assert OpenedAgreement.contract_event_name == 'OpenedAgreement'


def test_messages_QuorumReached(mkevent, decoded_msg, txhash_b, block_number):
    event = mkevent({'bountyGuid': 16577})
    assert decoded_msg(QuorumReached.serialize_message(event)) == {
        'block_number': block_number,
        'data': {
            'bounty_guid': '00000000-0000-0000-0000-0000000040c1'
        },
        'event': 'quorum',
        'txhash': txhash_b,
    }


def test_messages_RevealedAssertion(mkevent, decoded_msg, txhash_b, block_number):
    event = mkevent({
        'bountyGuid': 2,
        'author': '0xDF9246BB76DF876Cef8bf8af8493074755feb58c',
        'index': 10,
        'verdicts': 128,
        'nonce': 8,
        'numArtifacts': 4,
        'metadata': 'ZWbountyuri'
    })

    assert decoded_msg(RevealedAssertion.serialize_message(event)) == {
        'block_number': block_number,
        'data': {
            'author': '0xDF9246BB76DF876Cef8bf8af8493074755feb58c',
            'bounty_guid': '00000000-0000-0000-0000-000000000002',
            'index': 10,
            'metadata': [{
                'malware_family': 'EICAR',
                'scanner': {
                    'environment': {
                        'architecture': 'x86_64',
                        'operating_system': 'Linux'
                    }
                }
            }],
            'nonce': '8',
            'verdicts': [False, False, False, False, False, False, False, True]
        },
        'event': 'reveal',
        'txhash': txhash_b,
    }


def test_messages_SettleStateChallenged(mkevent, decoded_msg, addr1, txhash_b, block_number):
    event = mkevent({'challenger': addr1, 'sequence': 1688, 'settlementPeriodEnd': 229})
    assert decoded_msg(SettleStateChallenged.serialize_message(event)) == {
        'block_number': block_number,
        'data': {
            'challenger': '0x0000000000000000000000000000000000000001',
            'nonce': 1688,
            'settle_period_end': 229
        },
        'event': 'settle_challenged',
        'txhash': txhash_b,
    }


def test_messages_SettledBounty(mkevent, decoded_msg, addr1, txhash_b, block_number):
    event = mkevent({'bountyGuid': 16577, 'settler': addr1, 'payout': 1000})
    assert decoded_msg(SettledBounty.serialize_message(event)) == {
        'block_number': block_number,
        'data': {
            'bounty_guid': '00000000-0000-0000-0000-0000000040c1',
            'payout': 1000,
            'settler': '0x0000000000000000000000000000000000000001'
        },
        'event': 'settled_bounty',
        'txhash': txhash_b,
    }


def test_messages_StartedSettle(mkevent, decoded_msg, addr1, txhash_b, block_number):
    event = mkevent({'initiator': addr1, 'sequence': 1688, 'settlementPeriodEnd': 229})
    assert decoded_msg(StartedSettle.serialize_message(event)) == {
        'block_number': block_number,
        'data': {
            'initiator': '0x0000000000000000000000000000000000000001',
            'nonce': 1688,
            'settle_period_end': 229
        },
        'event': 'settle_started',
        'txhash': txhash_b,
    }


def test_messages_Transfer(mkevent, decoded_msg, pprint, addr1, addr2):
    assert pprint(Transfer.extract({
        'to': addr1,
        'from': addr2,
        'value': 1
    })) == {
        'from': '0x0000000000000000000000000000000000000002',
        'to': '0x0000000000000000000000000000000000000001',
        'value': '1'
    }


def test_messages_Undeprecated(mkevent, decoded_msg, txhash_b, block_number):
    assert Undeprecated.contract_event_name == 'Undeprecated'
    event = mkevent({'a': 1, 'hello': 'world', 'should_not_be_here': True})
    assert decoded_msg(Undeprecated.serialize_message(event)) == {
        'block_number': block_number,
        'data': {},
        'event': 'undeprecated',
        'txhash': txhash_b,
    }


def test_messages_WindowsUpdated(mkevent, decoded_msg, txhash_b, block_number):
    event = mkevent({'assertionRevealWindow': 100, 'arbiterVoteWindow': 105})
    assert decoded_msg(WindowsUpdated.serialize_message(event)) == {
        'block_number': block_number,
        'data': {
            'arbiter_vote_window': 105,
            'assertion_reveal_window': 100
        },
        'event': 'window_update',
        'txhash': txhash_b,
    }
