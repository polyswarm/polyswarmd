from flask import Blueprint

from polyswarmd.eth import web3, nectar_token
from polyswarmd.response import success, failure

balances = Blueprint('balances', __name__)


@balances.route('/<address>/<chain>/eth', methods=['GET'])
def get_balance_address_eth(address, chain):
    if not web3[chain].isAddress(address):
        return failure('Invalid address', 400)

    address = web3[chain].toChecksumAddress(address)
    return success(str(web3[chain].eth.getBalance(address)))


@balances.route('/<address>/<chain>/nct', methods=['GET'])
def get_balance_address_nct(address, chain):
    if not web3[chain].isAddress(address):
        return failure('Invalid address', 400)

    address = web3[chain].toChecksumAddress(address)
    return success(str(nectar_token[chain].functions.balanceOf(address).call()))
