import pytest
import polyswarmd

@pytest.fixture
def client():
    polyswarmd.app.config['TESTING'] = True
    client = polyswarmd.app.test_client()
    yield client
