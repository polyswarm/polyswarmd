import json
import os

from web3 import Web3, HTTPProvider
from web3.middleware import geth_poa_middleware

from polyswarmd.config import eth_uri, nectar_token_address, bounty_registry_address, whereami


def bind_contract(web3_, address, artifact):
    with open(os.path.abspath(os.path.join(whereami(), artifact)), 'r') as f:
        abi = json.load(f)['abi']

    return web3_.eth.contract(address=web3_.toChecksumAddress(address), abi=abi)


zero_address = '0x0000000000000000000000000000000000000000'

web3 = {}

# Create token bindings for each chain
bounty_registry = {}
nectar_token = {}
for chain in ('home', 'side'):
    temp = Web3(HTTPProvider(eth_uri[chain]))
    temp.middleware_stack.inject(geth_poa_middleware, layer=0)
    web3[chain] = temp
    nectar_token[chain] = bind_contract(
        web3[chain], nectar_token_address[chain],
        os.path.join('truffle', 'build', 'contracts', 'NectarToken.json'))

    bounty_registry[chain] = bind_contract(
        web3[chain], bounty_registry_address[chain],
        os.path.join('truffle', 'build', 'contracts', 'BountyRegistry.json'))


def check_transaction(web3, tx):
    receipt = web3.eth.waitForTransactionReceipt(tx)
    return receipt and receipt.status == 1


def bounty_fee():
    return 62500000000000000


def assertion_fee():
    return 62500000000000000


def bounty_amount_min():
    return 62500000000000000


def assertion_bid_min():
    return 62500000000000000
