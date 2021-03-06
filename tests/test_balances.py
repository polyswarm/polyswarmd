from .utils import failed, heck


def test_get_balance_total_stake(client, token_address, balances):
    assert client.get(f'/balances/{token_address}/staking/total').json == {
        'result': str(balances[token_address]),
        'status': 'OK'
    }

    assert failed(client.get(f'/balances/INVALID/staking/total'))


def test_get_balance_withdrawable_stake(client, token_address, balances):
    assert client.get(f'/balances/{token_address}/staking/withdrawable').json == {
        'result': str(balances[token_address]),
        'status': 'OK'
    }

    assert failed(client.get(f'/balances/INVALID/staking/withdrawable'))


def test_get_balance_address_eth(client, token_address):
    assert client.get(f'/balances/{token_address}/eth').json == heck({
        'result': heck.NONEMPTYSTR,
        'status': 'OK'
    })
