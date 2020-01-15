from urllib.parse import urlencode

import pytest

from .utils import heck, sane


@pytest.fixture
def tx_success_response(token_address, base_nonce):
    return {
        'result': {
            'transactions': [{
                'chainId': heck.IGNORE,
                'data': lambda s: s.startswith('0xa9059cbb') and len(s) == 138 and s.endswith('1'),
                'gas': heck.POSINT,
                'gasPrice': 0,
                'nonce': base_nonce,
                'to': heck.ETHADDR,
                'value': 0
            }]
        },
        'status': 'OK'
    }


@pytest.fixture
def tx_query_string(token_address, base_nonce):
    return {'account': token_address, 'base_nonce': base_nonce}


def test_deposit_funds_success(client, tx_success_response, tx_query_string):
    assert sane(
        response=client.post('/relay/deposit', query_string=tx_query_string, json={'amount': '1'}),
        expected=tx_success_response
    )


def test_withdrawal_funds_success(client, tx_success_response, tx_query_string):
    assert sane(
        response=client.post(
            '/relay/withdrawal', query_string=tx_query_string, json={'amount': '1'}
        ),
        expected=tx_success_response
    )


def test_withdrawal_funds_success(client, chain_config, token_address):
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
