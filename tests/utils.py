"""
This file contains utilities *FOR TESTING*, it should *NOT* contain tests of polyswarmd utilities
"""
from collections import UserDict
from collections.abc import Mapping
import json
from pathlib import Path
import string


class heck(UserDict):
    """MappingProxy which allows functions as value to overide inner equality checks"""

    def __init__(self, data):
        if not isinstance(data, Mapping):
            raise ValueError("Invalid type: %s" % type(data))
        super().__init__(data.copy())

    @classmethod
    def fixup(cls, actual, expected):
        """Checks if `expected` is callable & `expected(actual)` is truthy, returning `actual` or `expected`"""
        if isinstance(expected, Mapping) and len(expected) == len(actual):
            return {k: cls.fixup(actual[k], expected[k]) for k in expected}
        if isinstance(expected, list):
            return [cls.fixup(actual[i], expected[i]) for i in range(len(expected))]
        elif callable(expected):
            if expected(actual):
                return actual
            else:
                return 'EXPECT_CHECK_FAILURE=' + str(actual)
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
    def IGNORE(x) -> bool:
        return True


def sane(actual=None, response=None, expected=None):
    if response:
        actual = response.json
    return actual == heck(expected)


def read_chainfile(chain_name):
    chain_cfg_dir = Path('tests/fixtures/config/chain/').resolve()
    chain_filename = f'{chain_name}chain.json'
    with open(chain_cfg_dir.joinpath(chain_filename)) as ff:
        return {**{'chain_name': chain_name}, **json.load(ff)}
