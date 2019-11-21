import logging

from flask import Blueprint, g, request
import jsonschema
from jsonschema.exceptions import ValidationError

from polyswarmd import eth
from polyswarmd.chains import chain
from polyswarmd.eth import build_transaction
from polyswarmd.response import failure, success

logger = logging.getLogger(__name__)
staking = Blueprint('staking', __name__)


@staking.route('/parameters', methods=['GET'])
@chain
def get_staking_parameters():
    minimum_stake = g.chain.arbiter_staking.contract.functions.MINIMUM_STAKE().call()
    maximum_stake = g.chain.arbiter_staking.contract.functions.MAXIMUM_STAKE().call()
    vote_ratio_numerator = g.chain.arbiter_staking.contract.functions.VOTE_RATIO_NUMERATOR().call()
    vote_ratio_denominator = g.chain.arbiter_staking.contract.functions.VOTE_RATIO_DENOMINATOR(
    ).call()

    return success({
        'minimum_stake': minimum_stake,
        'maximum_stake': maximum_stake,
        'vote_ratio_numerator': vote_ratio_numerator,
        'vote_ratio_denominator': vote_ratio_denominator
    })


@staking.route('/deposit', methods=['POST'])
@chain
def post_arbiter_staking_deposit():
    account = g.chain.w3.toChecksumAddress(g.eth_address)
    base_nonce = int(request.args.get('base_nonce', g.chain.w3.eth.getTransactionCount(account)))

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

    total = g.chain.arbiter_staking.contract.functions.balanceOf(account).call()

    if amount + total >= eth.staking_total_max(g.chain.arbiter_staking.contract):
        return failure('Total stake above allowable maximum.', 400)

    transactions = [
        build_transaction(
            g.chain.nectar_token.contract.functions.approve(
                g.chain.arbiter_staking.contract.address, amount
            ), base_nonce
        ),
        build_transaction(
            g.chain.arbiter_staking.contract.functions.deposit(amount), base_nonce + 1
        ),
    ]

    return success({'transactions': transactions})


@staking.route('/withdraw', methods=['POST'])
@chain
def post_arbiter_staking_withdrawal():
    account = g.chain.w3.toChecksumAddress(g.eth_address)
    base_nonce = int(request.args.get('base_nonce', g.chain.w3.eth.getTransactionCount(account)))

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

    available = g.chain.arbiter_staking.contract.functions.withdrawableBalanceOf(account).call()

    if amount > available:
        return failure('Exceeds withdrawal eligible %s' % available, 400)

    transactions = [
        build_transaction(g.chain.arbiter_staking.contract.functions.withdraw(amount), base_nonce),
    ]

    return success({'transactions': transactions})
