import pytest


@pytest.fixture
def good_status(heck):
    return heck({
        'result': {
            'artifact_services': {
                'ipfs': {
                    'reachable': True
                }
            },
            'community': 'gamma',
            'home': {
                'block': lambda x: x > 0,
                'reachable': True,
                'syncing': False
            },
            'side': {
                'block': lambda x: x > 0,
                'reachable': True,
                'syncing': False
            }
        },
        'status': 'OK'
    })


def test_get_status(client, good_status):
    status = client.get('/status')
    assert good_status == status.json
