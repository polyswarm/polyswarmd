"""
   isort:skip_file
"""
from collections import UserDict
from collections.abc import Mapping

import string
import random
from pathlib import Path
import os
import pytest
import json
from unittest.mock import patch

import requests.adapters
from requests.models import Response


def let(obj, **kwargs):
    for attr, val in kwargs.items():
        setattr(obj, attr, val)
    return obj


# a list of function patches to be applied prior `import polyswarmd`
PRE_INIT_PATCHES = (
    # don't both with patching gevent methods inside pytest
    patch('gevent.monkey.patch_all', return_value=None),
    # # fake out the underlying ipfshttpclient connect
    # patch('ipfshttpclient.connect', return_value=True),
    # # replace requests.adapter's send method
    # patch.object(
    #     requests.adapters.HTTPAdapter, 'send', return_value=let(Response(), status_code=200)
    # ),
    # set `POLY_WORK` to be 'testing' (if not already set)
    patch('os.getenv', lambda *args, **kwargs: 'testing' if args[0] == 'POLY_WORK' else os.getenv)
)

for pa in PRE_INIT_PATCHES:
    pa.start()

# NOTE polyswarmd is structured such that merely importing a package in the `polyswarmd` namespace will
# raise an exception. Fixing this (e.g moving stuff outta src/polyswarmd/__init__.py) has been on the
# todo list for some time, but for now, we just patch up methods which have unsafe side effects to
# run unit tests without side-effects.
import polyswarmd
from polyswarmd.app import app as _app  # noqa

for pa in PRE_INIT_PATCHES:
    pa.stop()


@pytest.fixture
def community():
    return 'gamma'

@pytest.fixture
def base_nonce():
    return random.randint(2**15, 2**16)

@pytest.fixture
def token_address():
    return '0x4B1867c484871926109E3C47668d5C0938CA3527'


@pytest.fixture
def app():
    return _app


@pytest.fixture
def client(app):
    app.config['TESTING'] = True
    yield app.test_client()


@pytest.fixture
def ZERO_ADDRESS():
    from polyswarmd.views.eth import ZERO_ADDRESS
    return ZERO_ADDRESS


CHAINCFG = Path('tests/fixtures/config/chain/').resolve()

def _read_chain(chain_name):
    with open(CHAINCFG.joinpath(f'{chain_name}chain.json')) as ff:
        cobj = json.load(ff)
        cobj.update({'chain_name': chain_name})
        return cobj


@pytest.fixture(params=['home'])
def homechain(request):
    return _read_chain(request.param)


@pytest.fixture(params=['side'])
def sidechain(request):
    return _read_chain(request.param)


@pytest.fixture(params=['home', 'side'])
def chain(request):
    return _read_chain(request.param)


class ExpectedProxy(UserDict):
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

@pytest.fixture
def heck():
    return ExpectedProxy
