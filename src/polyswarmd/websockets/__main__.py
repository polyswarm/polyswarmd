import sys
from typing import Any, List


def run_doctests():
    from collections import namedtuple
    import doctest
    import json
    from pprint import pprint
    import ujson

    from . import json_schema, messages

    failures = 0

    fails, _tests = doctest.testmod(m=json_schema)
    failures += fails

    event_defaults = {
        'args': {},
        'event': 'test event',
        'logIndex': 19845,
        'transactionIndex': 1276,
        'transactionHash': (11).to_bytes(16, byteorder='big'),
        'address': '0xFACE0EEE000000000000000000000001',
        'blockHash': (90909090).to_bytes(16, byteorder='big'),
        'blockNumber': 117,
    }

    fields: List[str] = list(event_defaults.keys())
    defaults: List[Any] = list(event_defaults.values())

    class TestEvent(namedtuple('TestEvent', fields, defaults=defaults)):  # type: ignore
        """A test event, used for making standard events in doctesting"""

        def __getitem__(self, k):
            if (type(k) == str):
                return self.__getattribute__(k)
            return super().__getitem__(k)

    class TestChain:

        @property
        def blockNumber(self):
            return 117

    # Override _substitute_metadata so we can test `fetch_metadata' without network IO.
    # doctest.testmod does accept globals-setting parameters (`globs` & `extraglobs'),
    # but they haven't been as easy as just overwriting messages here
    def _mock_substitute_metadata(uri, validate):
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

    messages.MetadataHandler._substitute_metadata = _mock_substitute_metadata

    fails, _tests = doctest.testmod(
        m=messages,
        extraglobs={
            'pprint': pprint,
            'decoded_msg': lambda wsmsg: pprint(json.loads(bytes(wsmsg.message).decode('ascii'))),
            'mkevent': TestEvent,
            'addr1': "0x00000000000000000000000000000001",
            'addr2': "0x00000000000000000000000000000002",
            'chain1': TestChain()
        }
    )
    failures += fails

    return failures


if __name__ == "__main__":
    # make sure we don't start getting into 'reserved error code' territory'
    exit_code = min(126, run_doctests())
    sys.exit(exit_code)
