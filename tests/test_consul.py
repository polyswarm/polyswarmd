import io

import requests_mock

from polyswarmd.config.polyswarmd import PolySwarmd

def test_from_consul_configs():
    PolySwarmd.from_consul()
    pass
