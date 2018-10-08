import jsonschema
import logging
from jsonschema.exceptions import ValidationError
from flask import Blueprint, g, request

from polyswarmd import eth
from polyswarmd.eth import build_transaction
from polyswarmd.chains import chain
from polyswarmd.response import success, failure

logger = logging.getLogger(__name__)  # Init logger
staking = Blueprint('staking', __name__)


@staking.route('/parameters', methods=['GET'])
@chain
def get_staking_parameters():
    minimum_stake = g.arbiter_staking.functions.MINIMUM_STAKE().call()
    maximum_stake = g.arbiter_staking.functions.MAXIMUM_STAKE().call()
    vote_ratio_numerator = g.arbiter_staking.functions.VOTE_RATIO_NUMERATOR().call()
    vote_ratio_denominator = g.arbiter_staking.functions.VOTE_RATIO_DENOMINATOR().call()

    return success({
        'minimum_stake': minimum_stake,
        'maximum_stake': maximum_stake,
        'vote_ratio_numerator': vote_ratio_numerator,
        'vote_ratio_denominator': vote_ratio_denominator
    })


@staking.route('/deposit', methods=['POST'])
@chain
def post_arbiter_staking_deposit():
    account = g.web3.toChecksumAddress(g.eth_address)

    base_nonce = int(
        request.args.get('base_nonce', g.web3.eth.getTransactionCount(account)))

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

    total = g.arbiter_staking.functions.balanceOf(account).call()

    if amount + total >= eth.staking_total_max(g.arbiter_staking):
        return failure('Total stake above allowable maximum.', 400)

    transactions = [
        build_transaction(
            g.nectar_token.functions.approve(g.arbiter_staking.address, amount), base_nonce),
        build_transaction(
            g.arbiter_staking.functions.deposit(amount),  base_nonce + 1),
    ]

    return success({'transactions': transactions})


@staking.route('/withdraw', methods=['POST'])
@chain
def post_arbiter_staking_withdrawal():
    account = g.web3.toChecksumAddress(g.eth_address)

    base_nonce = int(
        request.args.get('base_nonce', g.web3.eth.getTransactionCount(account)))

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

    available = g.arbiter_staking.functions.withdrawableBalanceOf(account).call()

    if amount > available:
        return failure('Exceeds withdrawal eligible %s' % available, 400)

    transactions = [
        build_transaction(
            g.arbiter_staking.functions.withdraw(amount), base_nonce),
    ]

    return success({'transactions': transactions})
