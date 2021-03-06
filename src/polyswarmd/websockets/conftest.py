from collections import namedtuple
import json
from pprint import pprint

import pytest
import ujson

from polyswarmd.websockets import messages


@pytest.fixture(autouse=True)
def mock_md_fetch(monkeypatch):
    """Mock out the metadata-fetching implementation

    Override _substitute_metadata so we can test `fetch_metadata' without network IO.
    doctest.testmod does accept globals-setting parameters (`globs` & `extraglobs'), but they
    haven't been as easy as just overwriting messages here
    """

    def mock_sub(uri, validate):
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

        if validate:
            if validate(content):
                return content
            else:
                return None
        return uri

    monkeypatch.setattr(messages.MetadataHandler, "_substitute_metadata", mock_sub)


class mkevent:
    DEFAULT_BLOCK = 117
    ALTERNATE_BLOCK = 220

    def __init__(self, *args, **kwargs):
        event_default = {
            'args': {},
            'event': 'test event',
            'logIndex': 19845,
            'transactionIndex': 1276,
            'transactionHash': (11).to_bytes(16, byteorder='big'),
            'address': '0xFACE0EEE000000000000000000000001',
            'blockHash': (90909090).to_bytes(16, byteorder='big'),
            'blockNumber': self.DEFAULT_BLOCK,
        }
        for i, (attr, default) in enumerate(event_default.items()):
            if len(args) > i:
                setattr(self, attr, args[i])
            elif attr in kwargs:
                setattr(self, attr, kwargs[attr])
            else:
                setattr(self, attr, default)

    def __getitem__(self, k):
        if (type(k) == str):
            return self.__getattribute__(k)


@pytest.fixture(autouse=True)
def add_websockets_doctest_deps(doctest_namespace):
    TestChain = namedtuple('TestChain', ['blockNumber'])
    FakeFormatter = namedtuple('FakeFormatter', ['contract_event_name'])
    doctest_namespace['decoded_msg'] = lambda wsmsg: pprint(json.loads(wsmsg.decode('ascii')))
    doctest_namespace["chain1"] = TestChain(mkevent.DEFAULT_BLOCK)
    doctest_namespace["chain2"] = TestChain(mkevent.ALTERNATE_BLOCK)
    doctest_namespace["addr1"] = "0x00000000000000000000000000000001"
    doctest_namespace["addr2"] = "0x00000000000000000000000000000002"
    doctest_namespace["mkevent"] = mkevent
    doctest_namespace["pprint"] = pprint
    doctest_namespace['fake_formatter'] = FakeFormatter
    doctest_namespace['identity'] = lambda *args: args
    doctest_namespace['approx'] = pytest.approx
