import pytest
import polyswarmd

from polyswarmd.config import init_config

@pytest.fixture
def client():
    init_config
    polyswarmd.app.config['TESTING'] = True
    client = polyswarmd.app.test_client()
    yield client
