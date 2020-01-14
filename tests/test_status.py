import pytest
from polyswarmd.config.status import Status

@pytest.fixture
def status(community):
    return Status(community=community)


@pytest.mark.skip
def test_get_status(status):
    assert {'community': 'gamma'} == status.get_status()
