import logging

from flask import Blueprint, g

from polyswarmd.chains import chain
from polyswarmd.response import success, failure

logger = logging.getLogger(__name__)
balances = Blueprint('balances', __name__)


@balances.route('/<address>/eth', methods=['GET'])
@chain(account_required=False)
def get_balance_address_eth(address):
    if not g.chain.w3.isAddress(address):
        return failure('Invalid address', 400)

    address = g.chain.w3.toChecksumAddress(address)
    try:
        balance = g.chain.w3.eth.getBalance(address)
        return success(str(balance))
    except Exception:
        logger.exception('Unexpected exception retrieving ETH balance')
        return failure("Could not retrieve balance")


@balances.route('/<address>/staking/total', methods=['GET'])
@chain(account_required=False)
def get_balance_total_stake(address):
    if not g.chain.w3.isAddress(address):
        return failure('Invalid address', 400)
    address = g.chain.w3.toChecksumAddress(address)
    try:
        balance = g.chain.arbiter_staking.contract.functions.balanceOf(address).call()
        return success(str(balance))
    except Exception:
        logger.exception('Unexpected exception retrieving total staking balance')
        return failure("Could not retrieve balance")


@balances.route('/<address>/staking/withdrawable', methods=['GET'])
@chain(account_required=False)
def get_balance_withdrawable_stake(address):
    if not g.chain.w3.isAddress(address):
        return failure('Invalid address', 400)

    address = g.chain.w3.toChecksumAddress(address)
    try:
        balance = g.chain.arbiter_staking.contract.functions.withdrawableBalanceOf(address).call()
        return success(str(balance))
    except Exception:
        logger.exception('Unexpected exception retrieving withdrawable staking balance')
        return failure("Could not retrieve balance")


@balances.route('/<address>/nct', methods=['GET'])
@chain(account_required=False)
def get_balance_address_nct(address):
    if not g.chain.w3.isAddress(address):
        return failure('Invalid address', 400)

    address = g.chain.w3.toChecksumAddress(address)
    try:
        balance = g.chain.nectar_token.contract.functions.balanceOf(address).call()
        return success(str(balance))
    except Exception:
        logger.exception('Unexpected exception retrieving NCT balance')
        return failure("Could not retrieve balance")
