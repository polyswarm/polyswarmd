from .utils import heck


def test_get_bounties(client, token_address):
    response =  client.get('/bounties', query_string={'account': token_address})
    assert response.json == heck({
            'result': heck.ARRAY,
            'status': 'OK'
        })

def test_get_bounties(mock_w3, client, token_address, bounty_parameters):
    response = client.get('/bounties/parameters', query_string={'account': token_address})
    assert response.json == heck({'result': bounty_parameters, 'status': 'OK'})
