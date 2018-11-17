import io

import polyswarmd
import json

from polyswarmd import utils, app
from polyswarmd.eth import zero_address
from tests import client, test_account 

def test_post_to_state(client):
    expected = (b'{"result":{"state":"0x0000000000000000000000000000000000000000000000000000000000000001'
    b'00000000000000000000000000000000000000000000000000000000000004d20000000000000000000000004b1867c484'
    b'871926109e3c47668d5c0938ca35270000000000000000000000004b1867c484871926109e3c47668d5c0938ca35270000'
    b'00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
    b'00000000000000000000895440000000000000000000000000000000000000000000000000000000000000138800000000'
    b'00000000000000006f3b48ed359859f6f53e47048314878d8ce9c4c8000000000000000000000000000000000000000000'
    b'00000000000000000004d20000000000000000000000000000000000000000000000000000000000249f00000000000000'
    b'00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
    b'00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
    b'00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
    b'00000000000001000000000000000000000000000000000000000000000000000000000000000300000000000000000000'
    b'00000000000000000000000000000000000074657374"},"status":"OK"}\n')
    mock_state_dict = {
        'guid': '1234',
        'close_flag': 1,
        'nonce': 1234,
        'offer_amount': 2400000,
        'expert': test_account,
        'expert_balance': 5000,
        'ambassador': test_account,
        'ambassador_balance': 9000000,
        'msig_address': zero_address,
        'artifact_hash': 'null',
        'mask': [True, False],
        'verdicts': [True, True],
        'meta_data': 'test'
    }
    rv = client.post(
        '/offers/state?account={0}'.format(test_account),
        content_type='application/json',
        data=json.dumps(mock_state_dict)
    )

    assert rv.data == expected
