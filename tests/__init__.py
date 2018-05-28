import pytest
import polyswarmd

from polyswarmd.config import set_config

@pytest.fixture
def client():
    set_config()
    polyswarmd.app.config['TESTING'] = True
    client = polyswarmd.app.test_client()
    yield client
