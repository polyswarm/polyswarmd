from .utils import heck, sane


def test_get_bounties(client, token_address):
    assert sane(
        response=client.get('/bounties', query_string={'account': token_address}),
        expected=heck({
            'result': heck.ARRAY,
            'status': 'OK'
        })
    )
