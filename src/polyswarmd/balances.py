from flask import Blueprint, request, g

from polyswarmd.chains import chain
from polyswarmd.response import success, failure

balances = Blueprint('balances', __name__)

@balances.route('/<address>/eth', methods=['GET'])
@chain
def get_balance_address_eth(address):
    if not g.web3.isAddress(address):
        return failure('Invalid address', 400)

    address = g.web3.toChecksumAddress(address)
    try:
        balance = g.web3.eth.getBalance(address)
        return success(str(balance))
    except:
        return failure("Could not retrieve balance")

@balances.route('/<address>/staking/total', methods=['GET'])
@chain
def get_balance_total_stake(address):
    if not g.web3.isAddress(address):
        return failure('Invalid address', 400)
    address = g.web3.toChecksumAddress(address)
    try:
        balance = g.arbiter_staking.functions.balanceOf(address).call()
        return success(str(balance))
    except:
        return failure("Could not retrieve balance")


@balances.route('/<address>/staking/withdrawable', methods=['GET'])
@chain
def get_balance_withdrawable_stake(address):
    if not g.web3.isAddress(address):
        return failure('Invalid address', 400)

    address = g.web3.toChecksumAddress(address)
    try:
        balance = g.arbiter_staking.functions.withdrawableBalanceOf(address).call()
        return success(str(balance))
    except:
        return failure("Could not retrieve balance")


@balances.route('/<address>/nct', methods=['GET'])
@chain
def get_balance_address_nct(address):
    if not g.web3.isAddress(address):
        return failure('Invalid address', 400)

    address = g.web3.toChecksumAddress(address)
    try:
        balance = g.nectar_token.functions.balanceOf(address).call()
        return success(str(balance))
    except:
        return failure("Could not retrieve balance")
