from .utils import heck


def test_get_nonce(client, token_address):
    response = client.get('/nonce', query_string={'account': token_address}).json
    assert response == heck({'result': heck.UINT, 'status': 'OK'})
