"""
   isort:skip_file
"""
import os
import pytest
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
    # fake out the underlying ipfshttpclient connect
    patch('ipfshttpclient.connect', return_value=True),
    # replace requests.adapter's send method
    patch.object(
        requests.adapters.HTTPAdapter, 'send', return_value=let(Response(), status_code=200)
    ),
    # set `POLY_WORK` to be 'testing' (if not already set)
    patch('os.getenv', lambda *args, **kwargs: 'testing' if args[0] == 'POLY_WORK' else os.getenv)
)

for patch in PRE_INIT_PATCHES: patch.start()

# NOTE polyswarmd is structured such that merely importing a package in the `polyswarmd` namespace will
# raise an exception. Fixing this (e.g moving stuff outta src/polyswarmd/__init__.py) has been on the
# todo list for some time, but for now, we just patch up methods which have unsafe side effects to
# run unit tests without side-effects.
import polyswarmd   # noqa

for patch in PRE_INIT_PATCHES: patch.stop()

@pytest.fixture
def community():
    return 'gamma'

@pytest.fixture
def token_address():
    return '0x4B1867c484871926109E3C47668d5C0938CA3527'


@pytest.fixture
def app():
    yield polyswarmd.app


@pytest.fixture
def client(app):
    app.config['TESTING'] = True
    yield polyswarmd.app.test_client()


@pytest.fixture
def ZERO_ADDRESS():
    from polyswarmd.views.eth import ZERO_ADDRESS
    return ZERO_ADDRESS
