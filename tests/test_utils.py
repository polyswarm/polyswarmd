import pytest
import ujson as json

import polyswarmd.utils


def test_to_padded_hex():
    assert polyswarmd.utils.to_padded_hex("0xabcd").endswith("abcd")
    assert polyswarmd.utils.to_padded_hex(15).endswith("f")
    assert polyswarmd.utils.to_padded_hex("AAAA").endswith("41414141")
    assert polyswarmd.utils.to_padded_hex(b"AAAA").endswith("41414141")


def test_bool_list_to_int():
    bool_list = polyswarmd.utils.bool_list_to_int([True, True, False, True])
    expected = 11
    assert bool_list == expected


def test_int_to_bool_list():
    bool_list = polyswarmd.utils.int_to_bool_list(11)
    expected = [True, True, False, True]
    assert bool_list == expected


def test_safe_int_to_bool_list():
    bool_list = polyswarmd.utils.safe_int_to_bool_list(0, 5)
    expected = [False, False, False, False, False]
    assert bool_list == expected


def test_safe_int_to_bool_list_leading_zeros():
    bool_list = polyswarmd.utils.safe_int_to_bool_list(1, 5)
    expected = [True, False, False, False, False]
    assert bool_list == expected


@pytest.mark.skip(reason='waiting on dump of input inside getOfferState() run')
def test_state_to_dict(client, token_address, app, ZERO_ADDRESS):
    with app.app_context():
        token = app.config['POLYSWARMD'].chains['home'].nectar_token.address
        w3 = app.config['POLYSWARMD'].chains['home'].w3
        mock_state_dict = {
            'guid': '3432',
            'close_flag': 1,
            'nonce': 10,
            'offer_amount': 100,
            'expert': token_address,
            'expert_balance': 1234,
            'ambassador': token_address,
            'ambassador_balance': 1234,
            'msig_address': ZERO_ADDRESS,
            'artifact_hash': 'null',
            'mask': [True],
            'verdicts': [True],
            'meta_data': 'test'
        }
        rv = client.post(
            f'/offers/state?account={token_address}',
            content_type='application/json',
            data=json.dumps(mock_state_dict)
        )
        state = rv.json['result']['state']
        expected = {
            'nonce': 10,
            'offer_amount': 100,
            'msig_address': ZERO_ADDRESS,
            'ambassador_balance': 1234,
            'expert_balance': 1234,
            'ambassador': token_address,
            'expert': token_address,
            'is_closed': 1,
            'token': w3.toChecksumAddress(token),
            'mask': [True],
            'verdicts': [True]
        }

        assert polyswarmd.utils.state_to_dict(state) == expected
