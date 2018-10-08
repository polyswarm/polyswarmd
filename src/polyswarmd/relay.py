import jsonschema
import logging
from jsonschema.exceptions import ValidationError

from flask import Blueprint, g, request

from polyswarmd.response import success, failure
from polyswarmd.chains import chain
from polyswarmd.eth import build_transaction

logger = logging.getLogger(__name__)  # Init logger
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


def send_funds_from():
    # Grab correct versions by chain type
    account = g.web3.toChecksumAddress(g.eth_address)

    base_nonce = int(
        request.args.get('base_nonce', g.web3.eth.getTransactionCount(account)))

    if not g.erc20_relay_address or not g.web3.isAddress(g.erc20_relay_address):
        return failure('ERC20 Relay misconfigured', 500)
    erc20_relay_address = g.web3.toChecksumAddress(g.erc20_relay_address)

    schema = {
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
    }

    body = request.get_json()
    try:
        jsonschema.validate(body, schema)
    except ValidationError as e:
        return failure('Invalid JSON: ' + e.message, 400)

    amount = int(body['amount'])

    transactions = [
        build_transaction(
            g.nectar_token.functions.transfer(erc20_relay_address, amount), base_nonce),
    ]

    return success({'transactions': transactions})
