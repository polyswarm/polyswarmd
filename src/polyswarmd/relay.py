import jsonschema
from jsonschema.exceptions import ValidationError

from flask import Blueprint, request

from polyswarmd.response import success, failure
from polyswarmd.eth import web3 as web3_chains, build_transaction, nectar_token as nectar_chains
from polyswarmd.config import erc20_relay_address as erc20_chains

relay = Blueprint('relay', __name__)


@relay.route('/deposit', methods=['POST'])
def deposit_funds():
    # Move funds from home to side
    return send_funds_from('home')


@relay.route('/withdrawal', methods=['POST'])
def withdraw_funds():
    # Move funds from side to home
    return send_funds_from('side')


def send_funds_from(chain):
    # Grab correct versions by chain type
    web3 = web3_chains[chain]
    nectar_token = nectar_chains[chain]
    erc20_relay_address = erc20_chains[chain]

    account = request.args.get('account')
    if not account or not web3.isAddress(account):
        return failure('Source account required', 401)
    account = web3.toChecksumAddress(account)

    base_nonce = int(
        request.args.get('base_nonce', web3.eth.getTransactionCount(account)))

    if not erc20_relay_address or not web3.isAddress(erc20_relay_address):
        return failure('ERC20 Relay misconfigured', 500)
    erc20_relay_address = web3.toChecksumAddress(erc20_relay_address)

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
            nectar_token.functions.transfer(erc20_relay_address, amount),
            chain, base_nonce),
    ]

    return success({'transactions': transactions})
