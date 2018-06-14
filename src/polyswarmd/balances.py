from flask import Blueprint, request

from polyswarmd.eth import web3 as web3_chains, nectar_token as nectar_chains
from polyswarmd.response import success, failure

balances = Blueprint('balances', __name__)


@balances.route('/<address>/eth', methods=['GET'])
def get_balance_address_eth(address):
    chain = request.args.get('chain')
    if not chain:
        chain = 'home'
    elif chain != 'side' and chain != 'home':
        return failure('Chain must be either home or side', 400)

    web3 = web3_chains[chain]
    nectar_token = nectar_chains[chain]

    if not web3.isAddress(address):
        return failure('Invalid address', 400)

    address = web3.toChecksumAddress(address)
    try:
        balance = web3.eth.getBalance(address)
        return success(str(balance))
    except:
        return failure("Could not retrieve balance")


@balances.route('/<address>/nct', methods=['GET'])
def get_balance_address_nct(address):
    chain = request.args.get('chain')
    if not chain:
        chain = 'home'
    elif chain != 'side' and chain != 'home':
        return failure('Chain must be either home or side', 400)

    web3 = web3_chains[chain]
    nectar_token = nectar_chains[chain]

    if not web3.isAddress(address):
        return failure('Invalid address', 400)

    address = web3.toChecksumAddress(address)
    try:
        balance = nectar_token.functions.balanceOf(address).call()
        return success(str(balance))
    except:
        return failure("Could not retrieve balance")
