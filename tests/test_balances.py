from .utils import heck, sane


def test_get_balance_address_eth(client, token_address):
    assert sane(
        response=client.get(f'/balances/{token_address}/eth'),
        expected=heck({
            'result': heck.NONEMPTYSTR,
            'status': 'OK'
        })
    )
