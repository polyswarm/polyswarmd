"""
NOTE: These tests were automatically translated and are therefore a bit wonky.

Feel free to make it better
"""
from collections import namedtuple
import json

import pytest
import ujson
from web3.datastructures import AttributeDict

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

from .fixtures.messages import (
    assertion_metadata,
    block_hash,
    bounty_artifact_uri,
    assertion_artifact_uri,
    bounty_metadata,
    expected_contract_event_messages,
    expected_extractions,
    log_index,
    transaction_index,
    txhash_b,
    txhash_bv,
)

FakeChain = namedtuple('FakeChain', ['blockNumber'])
FakeFormatter = namedtuple('FakeFormatter', ['contract_event_name'])


@pytest.fixture
def mkevent(block_number, token_address):

    def to_mkevent(event_args):
        return AttributeDict.recursive({
            'args': event_args,
            'event': 'test_event',
            'logIndex': log_index,
            'transactionIndex': transaction_index,
            'transactionHash': txhash_b,
            'address': token_address,
            'blockHash': block_hash,
            'blockNumber': block_number,
        })

    return to_mkevent


@pytest.fixture
def decoded_msg():

    def _impl(msg):
        return json.loads(msg.decode('ascii'))

    return _impl


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
            bounty_artifact_uri: ujson.dumps([bounty_metadata]),
            assertion_artifact_uri: ujson.dumps([assertion_metadata])
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


def test_messages_LatestEvent(mkevent, decoded_msg, block_number):
    LE = LatestEvent.make(FakeChain(block_number))
    LA = LatestEvent.make(FakeChain(block_number + 1))
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


@pytest.mark.parametrize('extraction', expected_extractions)
def test_extraction(extraction, mkevent, decoded_msg, mock_md_fetch, block_number):
    cls, data, expected = extraction[:3]
    assert cls.contract_event_name == cls.__name__
    assert cls.extract(data) == expected


@pytest.mark.parametrize('emsg', expected_contract_event_messages)
def test_serialization(emsg, mkevent, decoded_msg, mock_md_fetch, block_number):
    cls, data, expected, event = emsg
    assert cls.contract_event_name == cls.__name__
    assert decoded_msg(cls.serialize_message(mkevent(data))) == {
        'block_number': block_number,
        'data': expected,
        'txhash': txhash_bv,
        'event': event,
    }
