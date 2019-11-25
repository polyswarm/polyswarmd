import sys
from typing import Any, List


def run_doctests():
    from . import json_schema, messages
    from pprint import pprint
    from collections import namedtuple
    import doctest
    import json

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
    messages._substitute_metadata = lambda uri, validate: {
        'malware_family': 'EICAR',
        'scanner': {
            'environment': {
                'architecture': 'x86_64',
                'operating_system': 'Linux'
            }
        }
    }
    fails, _tests = doctest.testmod(
        m=messages,
        extraglobs={
            'pprint': pprint,
            'decoded_msg': lambda wsmsg: pprint(json.loads(wsmsg.message.decode('ascii'))),
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
