import pytest
import polyswarmd

from polyswarmd.config import Config

test_account='0x4B1867c484871926109E3C47668d5C0938CA3527'

@pytest.fixture
def client():
    polyswarmd.app.config['POLYSWARMD'] = Config.auto()
    polyswarmd.app.config['TESTING'] = True
    client = polyswarmd.app.test_client()
    yield client
