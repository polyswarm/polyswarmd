import jsonschema
from jsonschema.exceptions import ValidationError
from flask import Blueprint, g, request

from polyswarmd import eth
from polyswarmd.eth import web3 as web3_chains, build_transaction, nectar_token as nectar_chains, arbiter_staking as arbiter_chains
from polyswarmd.response import success, failure

staking = Blueprint('staking', __name__)


@staking.route('/deposit', methods=['POST'])
def post_arbiter_staking_deposit():
    # Must read chain before account to have a valid web3 ref
    chain = request.args.get('chain', 'home')
    if chain != 'side' and chain != 'home':
        return failure('Chain must be either home or side', 400)

    web3 = web3_chains[chain]
    nectar_token = nectar_chains[chain]
    arbiter_staking = arbiter_chains[chain]
    account = web3.toChecksumAddress(g.eth_address)

    base_nonce = int(
        request.args.get('base_nonce', web3.eth.getTransactionCount(account)))

    schema = {
        'type': 'object',
        'properties': {
            'amount': {
                'type': 'string',
                'minLength': 1,
                'maxLength': 100,
                'pattern': r'^\d+$',
            }
        },
        'required': ['amount'],
    }

    body = request.get_json()
    try:
        jsonschema.validate(body, schema)
    except ValidationError as e:
        return failure('Invalid JSON: ' + e.message, 400)

    amount = int(body['amount'])

    total = arbiter_staking.functions.balanceOf(account).call()

    if amount + total >= eth.staking_total_max(chain):
        return failure('Total stake above allowable maximum.', 400)

    transactions = [
        build_transaction(
            nectar_token.functions.approve(arbiter_staking.address, amount), chain, base_nonce),
        build_transaction(
            arbiter_staking.functions.deposit(amount), chain, base_nonce + 1),
    ]

    return success({'transactions': transactions})


@staking.route('/withdraw', methods=['POST'])
def post_arbiter_staking_withdrawal():
    # Must read chain before account to have a valid web3 ref
    chain = request.args.get('chain', 'home')
    if chain != 'side' and chain != 'home':
        return failure('Chain must be either home or side', 400)

    web3 = web3_chains[chain]
    arbiter_staking = arbiter_chains[chain]
    account = web3.toChecksumAddress(g.eth_address)

    base_nonce = int(
        request.args.get('base_nonce', web3.eth.getTransactionCount(account)))

    schema = {
        'type': 'object',
        'properties': {
            'amount': {
                'type': 'string',
                'minLength': 1,
                'maxLength': 100,
                'pattern': r'^\d+$',
            }
        },
        'required': ['amount'],
    }

    body = request.get_json()
    try:
        jsonschema.validate(body, schema)
    except ValidationError as e:
        return failure('Invalid JSON: ' + e.message, 400)

    amount = int(body['amount'])

    available = arbiter_staking.functions.withdrawableBalanceOf(account).call()

    if amount > available:
        return failure('Exceeds withdrawal eligible %s' % available, 400)

    transactions = [
        build_transaction(
            arbiter_staking.functions.withdraw(amount), chain, base_nonce),
    ]

    return success({'transactions': transactions})
