import requests.adapters
import requests.models

import pytest
from unittest.mock import patch


def send(self, req, *args, **kwargs):
    response = requests.models.Response()
    response.status_code = 200
    response.headers = {}
    response.encoding = 'utf8'
    # response.raw = None
    response.reason = 'OK'
    response.url = req.url
    # Give the Response some context.
    response.request = req
    response.connection = self
    return response


@patch('gevent.monkey.patch_all', lambda *args: None)
@patch('ipfshttpclient.connect', lambda *args, **kwargs: True)
@patch.object(requests.adapters.HTTPAdapter, 'send', send)
def safe_polyswarmd_import():
    # NOTE polyswarmd is structured such that merely importing a package in the `polyswarmd` namespace will
    # raise an exception. Fixing this (e.g moving stuff outta src/polyswarmd/__init__.py) has been on the
    # todo list for some time, but for now, we just patch up methods which have unsafe side effects to
    # run unit tests without side-effects.
    import polyswarmd


safe_polyswarmd_import()
