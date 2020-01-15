from urllib.parse import urlencode
import pytest


@pytest.fixture
def transaction_success(homechain, heck, token_address, base_nonce):
    req_qstr = urlencode({'account': token_address, 'base_nonce': base_nonce})
    res_body = heck({
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
    })
    return req_qstr, res_body


def test_deposit_funds_success(client, transaction_success):
    qstr, body = transaction_success
    assert client.post('/relay/deposit?' + qstr, json={'amount': '1'}).json == body


def test_withdrawal_funds_success(client, transaction_success):
    qstr, body = transaction_success
    assert client.post('/relay/withdrawal?' + qstr, json={'amount': '1'}).json == body


def test_withdrawal_funds_success(client, chain, token_address):
    resp = client.get(
        f'/relay/fees?' + urlencode({
            'chain': chain["chain_name"],
            'account': token_address
        })
    ).json
    assert resp['status'] == 'OK'
    fees = resp['result']['fees']
    assert isinstance(fees, int)
    assert fees >= 0
