import logging

import fastjsonschema
from flask import Blueprint, g, request

from polyswarmd.utils.decorators.chains import chain
from polyswarmd.views.eth import build_transaction
from polyswarmd.utils.response import failure, success

logger = logging.getLogger(__name__)
relay = Blueprint('relay', __name__)


@relay.route('/deposit', methods=['POST'])
@chain(chain_name='home')
def deposit_funds():
    # Move funds from home to side
    return send_funds_from()


@relay.route('/withdrawal', methods=['POST'])
@chain(chain_name='side')
def withdraw_funds():
    # Move funds from side to home
    return send_funds_from()


@relay.route('/fees', methods=['GET'])
@chain
def fees():
    return success({'fees': g.chain.erc20_relay.functions.fees().call()})


_send_funds_from_schema = fastjsonschema.compile({
    'type': 'object',
    'properties': {
        'amount': {
            'type': 'string',
            'minLength': 1,
            'maxLength': 64,
            'pattern': r'^\d+$',
        },
    },
    'required': ['amount'],
})


def send_funds_from():
    # Grab correct versions by chain type
    account = g.chain.w3.toChecksumAddress(g.eth_address)
    base_nonce = int(request.args.get('base_nonce', g.chain.w3.eth.getTransactionCount(account)))
    erc20_relay_address = g.chain.w3.toChecksumAddress(g.chain.erc20_relay.address)

    body = request.get_json()
    try:
        _send_funds_from_schema(body)
    except fastjsonschema.JsonSchemaException as e:
        return failure('Invalid JSON: ' + e.message, 400)

    amount = int(body['amount'])

    transactions = [
        build_transaction(
            g.chain.nectar_token.contract.functions.transfer(erc20_relay_address, amount), base_nonce
        ),
    ]

    return success({'transactions': transactions})
