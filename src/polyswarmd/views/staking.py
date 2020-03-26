import logging

import fastjsonschema
from flask import Blueprint, g, request

from polyswarmd.utils.decorators.chains import chain
from polyswarmd.utils.response import failure, success
from polyswarmd.views import eth
from polyswarmd.views.eth import build_transaction

logger = logging.getLogger(__name__)
staking: Blueprint = Blueprint('staking', __name__)


@staking.route('/parameters', methods=['GET'])
@staking.route('/parameters/', methods=['GET'])
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


_post_arbiter_staking_deposit_schema = fastjsonschema.compile({
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
})


@staking.route('/deposit', methods=['POST'])
@staking.route('/deposit/', methods=['POST'])
@chain
def post_arbiter_staking_deposit():
    account = g.chain.w3.toChecksumAddress(g.eth_address)
    base_nonce = int(request.args.get('base_nonce', g.chain.w3.eth.getTransactionCount(account)))

    body = request.get_json()
    try:
        _post_arbiter_staking_deposit_schema(body)
    except fastjsonschema.JsonSchemaException as e:
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


_post_arbiter_staking_withdrawal_schema = fastjsonschema.compile({
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
})


@staking.route('/withdraw', methods=['POST'])
@staking.route('/withdraw/', methods=['POST'])
@chain
def post_arbiter_staking_withdrawal():
    account = g.chain.w3.toChecksumAddress(g.eth_address)
    base_nonce = int(request.args.get('base_nonce', g.chain.w3.eth.getTransactionCount(account)))
    body = request.get_json()
    try:
        _post_arbiter_staking_withdrawal_schema(body)
    except fastjsonschema.JsonSchemaException as e:
        return failure('Invalid JSON: ' + e.message, 400)

    amount = int(body['amount'])

    available = g.chain.arbiter_staking.contract.functions.withdrawableBalanceOf(account).call()

    if amount > available:
        return failure('Exceeds withdrawal eligible %s' % available, 400)

    transactions = [
        build_transaction(g.chain.arbiter_staking.contract.functions.withdraw(amount), base_nonce),
    ]

    return success({'transactions': transactions})
