from urllib.parse import urlencode

import pytest

from polyswarmd.views.eth import TRANSFER_SIGNATURE_HASH as TX_SIG_HASH

from .utils import heck


@pytest.fixture
def tx_success_response(token_address, base_nonce):
    return heck({
        'result': {
            'transactions': [{
                'chainId': heck.IGNORE,
                'data': lambda s: s[2:].startswith(TX_SIG_HASH) and len(s) > len(TX_SIG_HASH) + 32,
                'gas': heck.POSINT,
                'gasPrice': 0,
                'nonce': base_nonce,
                'to': heck.ETHADDR,
                'value': 0
            }]
        },
        'status': 'OK'
    })


@pytest.fixture
def tx_query_string(token_address, base_nonce):
    return {'account': token_address, 'base_nonce': base_nonce}


def test_deposit_funds_success(client, tx_success_response, tx_query_string):
    response = client.post('/relay/deposit', query_string=tx_query_string, json={'amount': '1'})
    assert response.json == tx_success_response


def test_withdrawal_funds_success(client, tx_success_response, tx_query_string):
    response = client.post(
            '/relay/withdrawal', query_string=tx_query_string, json={'amount': '1'}
        )
    assert response.json == tx_success_response


def test_fees_endpoint(client, chain_config, token_address):
    resp = client.get(
        f'/relay/fees?' + urlencode({
            'chain': chain_config["chain_name"],
            'account': token_address
        })
    ).json
    assert resp['status'] == 'OK'
    fees = resp['result']['fees']
    assert isinstance(fees, int)
    assert fees >= 0
