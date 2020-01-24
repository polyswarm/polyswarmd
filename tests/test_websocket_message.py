"""
NOTE: These tests were automatically translated and are therefore a bit wonky.

Feel free to make it better
"""
from collections import namedtuple
import json
from typing import Any, Mapping, Optional, Tuple, Type, Union

import pytest
import ujson
from web3.datastructures import AttributeDict

from polyswarmd.websockets import types
from polyswarmd.websockets.messages import LatestEvent

from .fixtures.messages import (
    block_hash,
    bounty_artifact_uri,
    bounty_metadata,
    log_index,
    reveal_artifact_uri,
    reveal_metadata,
    serializations,
    transaction_index,
    txhash_b,
    txhash_bv,
)

FakeChain = namedtuple('FakeChain', ['blockNumber'])


def decoded_msg(msg):
    return json.loads(msg.decode('ascii'))


def to_pytest_param(
    fx: Tuple[Union[Type, Tuple[Type, str]], Mapping[str, Any], Mapping[str, Any], Optional[str]]
):
    head, *tail = fx
    # handle (Class, 'test_name')
    if isinstance(head, tuple):
        cls, name = head
        fixture = (cls, *tail)
    # otherwise we just use the tested class's name
    else:
        name = head.__name__
        fixture = fx
    return pytest.param(fixture, id=name)


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
            reveal_artifact_uri: ujson.dumps([reveal_metadata])
        }
        content = ''
        if uri in fake_uris:
            content = json.loads(fake_uris[uri])

        if cls._metadata_validator:
            if cls._metadata_validator(content):
                return content
            else:
                return None
        return uri

    monkeypatch.setattr(types.ArtifactMetadata, "substitute", mock_sub)


def test_messages_LatestEvent(mkevent, block_number):
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


@pytest.mark.parametrize('extraction', map(to_pytest_param, serializations))
def test_extraction(extraction, mkevent, mock_md_fetch, block_number):
    cls, data, expected, *_ = extraction
    assert cls.contract_event_name == cls.__name__
    assert cls.extract(data) == expected


@pytest.mark.parametrize('emsg', map(to_pytest_param, filter(lambda l: len(l) > 3, serializations)))
def test_serialization(emsg, mkevent, mock_md_fetch, block_number):
    cls, data, expected, event = emsg
    assert cls.contract_event_name == cls.__name__
    assert decoded_msg(cls.serialize_message(mkevent(data))) == {
        'block_number': block_number,
        'data': expected,
        'txhash': txhash_bv,
        'event': event,
    }
