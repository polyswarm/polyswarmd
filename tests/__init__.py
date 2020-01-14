import requests.adapters
import requests.models
import ipfshttpclient

import pytest
from unittest.mock import patch

@pytest.fixture
def client_config():
    return {
        "artifact": {
            "max_size": 34603008,
            "fallback_max_size": 10485760,
            "limit": 256,
            "library": {
                "module": "polyswarmd.services.artifact.ipfs",
                "class_name": "IpfsServiceClient",
                "args": [
                    "http://ipfs:5001"
                ]
            }
        },
        "community": "gamma",
        "eth": {
            "trace_transactions": True,
            "consul": {
                "uri": "http://consul:8500"
            }
        },
        "profiler": {
            "enabled": False
        },
        "redis": {
            "uri": "redis://redis:6379"
        },
        "websocket": {
            "enabled": True
        },
        "requests_session": FuturesSession(executor=ThreadPoolExecutor(4), adapter_kwargs={'max_retries': 2}),
        "threadpool": ThreadPoolExecutor(),
        "check_block_limit": False,
        "testing": True,
    }


@pytest.fixture
def polyswarmd_client(client_config):
    return PolySwarmd(client_config)

def send(self, req, *args, **kwargs):
    response = requests.models.Response()

    # Fallback to None if there's no status_code, for whatever reason.
    response.status_code = 200

    response.headers = {}

    # Set encoding.
    response.encoding = 'utf8'
    # response.raw = None
    response.reason = 'OK'
    response.url = req.url

    # Give the Response some context.
    response.request = req
    response.connection = self
    return response


@patch('ipfshttpclient.connect', lambda *args, **kwargs: True)
@patch.object(requests.adapters.HTTPAdapter, 'send', send)
def do_import():
    import polyswarmd

do_import()
