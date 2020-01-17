"""
This file contains utilities *FOR TESTING*, it should *NOT* contain tests of polyswarmd utilities
"""
from collections import UserDict
from collections.abc import Collection, Mapping
import json
import string


class heck(UserDict):
    """MappingProxy which allows functions as value to overide inner equality checks"""
    IGNORE = b'\x03'
    FAILED = b'\x15'

    def __init__(self, data):
        if not isinstance(data, Mapping):
            raise ValueError("Invalid type: %s" % type(data))
        super().__init__(data.copy())

    def fixup(self, actual, expected):
        """Checks if `expected` is callable & `expected(actual)` is truthy, returning `actual` or `expected`"""
        if isinstance(expected, Collection) and isinstance(actual, Collection):
            if isinstance(expected, Mapping):
                return {k: self.fixup(actual[k], expected[k]) for k in expected}
            elif isinstance(expected, list):
                return [self.fixup(actual[i], expected[i]) for i, _ in enumerate(expected)]
        elif callable(expected):
            return actual if expected(actual) else self.FAILED
        elif expected == self.IGNORE:
            return actual
        return expected

    def __eq__(self, actual):
        """Checks if ACTUAL is identical to EXPECTED, all funcs in actual are evaluated with ACTUAL 'cousin'"""
        return actual == self.fixup(actual, expected=self.data)

    # -----------------------------------

    @staticmethod
    def ETHADDR(addr: str) -> bool:
        addr = (addr[2:] if addr.startswith('0x') else addr).lower()
        return all(ch in string.hexdigits for ch in addr)

    @staticmethod
    def POSINT(num: int) -> bool:
        try:
            return num > 0
        except Exception:
            return False

    @staticmethod
    def UINT(num: int) -> bool:
        try:
            return num >= 0
        except Exception:
            return False

    @staticmethod
    def ARRAY(x) -> bool:
        return isinstance(x, list)

    @staticmethod
    def NONEMPTYSTR(x: str) -> bool:
        return isinstance(x, str) and len(x) > 0


def failed(response):
    return (response.status_code >= 400) or response.json.get('STATUS') == 'FAIL'


def read_chain_cfg(chain_name):
    cfgpath = f'tests/fixtures/config/chain/{chain_name}chain.json'
    return {'chain_name': chain_name, **json.load(open(cfgpath))}
