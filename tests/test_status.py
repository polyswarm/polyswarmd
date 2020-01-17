from .utils import heck


def test_get_status(client):
    assert client.get('/status').json == heck({
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
