from flask import Blueprint

from polyswarmd.eth import web3, nectar_token
from polyswarmd.response import success, failure

balances = Blueprint('balances', __name__)


@balances.route('/<address>/eth', methods=['GET'])
def get_balance_address_eth(address):
    if not web3.isAddress(address):
        return failure('Invalid address', 400)

    address = web3.toChecksumAddress(address)
    return success(str(web3.eth.getBalance(address)))


@balances.route('/<address>/nct', methods=['GET'])
def get_balance_address_nct(address):
    if not web3.isAddress(address):
        return failure('Invalid address', 400)

    address = web3.toChecksumAddress(address)
    return success(str(nectar_token.functions.balanceOf(address).call()))
