import pytest

from .utils import sane


def test_get_status(client):
    assert sane(
        response=client.get('/status'),
        expected={
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
        }
    )
