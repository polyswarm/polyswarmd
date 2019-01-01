import io

import polyswarmd
import json

from polyswarmd import utils, app
from polyswarmd.eth import ZERO_ADDRESS
from tests import client, test_account

def test_bool_list_to_int():
    bool_list = utils.bool_list_to_int([True, True, False, True])
    expected = 11
    assert bool_list == expected

def test_int_to_bool_list():
    bool_list = utils.int_to_bool_list(11)
    expected = [True, True, False, True]
    assert bool_list == expected

def test_safe_int_to_bool_list():
    bool_list = utils.safe_int_to_bool_list(0, 5)
    expected = [False, False, False, False, False]
    assert bool_list == expected

def test_state_to_dict(client):
    with app.app_context():
        token = app.config['POLYSWARMD'].chains['home'].nectar_token.address
        w3 = app.config['POLYSWARMD'].chains['home'].w3
        mock_state_dict = {
            'guid': '3432',
            'close_flag': 1,
            'nonce': 10,
            'offer_amount': 100,
            'expert': test_account,
            'expert_balance': 1234,
            'ambassador': test_account,
            'ambassador_balance': 1234,
            'msig_address': ZERO_ADDRESS,
            'artifact_hash': 'null',
            'mask': [True],
            'verdicts': [True],
            'meta_data': 'test'
        }
        rv = client.post(
            '/offers/state?account={0}'.format(test_account),
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
            'ambassador': test_account,
            'expert': test_account,
            'is_closed': 1,
            'token': w3.toChecksumAddress(token),
            'mask': [True],
            'verdicts': [True]
        }

        assert utils.state_to_dict(state) == expected
 