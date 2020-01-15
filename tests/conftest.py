"""
   isort:skip_file
"""
import random
import os
import pytest
from unittest.mock import patch

from .utils import read_chainfile
import requests.adapters  # noqa
from requests.models import Response  # noqa


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
import polyswarmd  # noqa
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


# XXX: if someone knows how to artificially restrict pytest fixtures, please let me know - zv
@pytest.fixture(params=['home'])
def homechain(request):
    return read_chainfile(request.param)


@pytest.fixture(params=['side'])
def sidechain(request):
    return read_chainfile(request.param)


@pytest.fixture(params=['home', 'side'])
def chain(request):
    return read_chainfile(request.param)
