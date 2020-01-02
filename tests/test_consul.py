import io

import requests_mock

from polyswarmd.config.config import Config

def test_from_consul_configs():
    Config.from_consul()
    pass
