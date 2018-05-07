import os
import json

from polyswarmd.config import eth_uri, nectar_token_address, bounty_registry_address, whereami
from web3 import Web3, HTTPProvider
from web3.middleware import geth_poa_middleware

web3 = Web3(HTTPProvider(eth_uri))
web3.middleware_stack.inject(geth_poa_middleware, layer=0)

def bind_contract(address, artifact):
    with open(os.path.abspath(os.path.join(whereami(), artifact)), 'r') as f:
        abi = json.load(f)['abi']

    return web3.eth.contract(address=web3.toChecksumAddress(address), abi=abi)

zero_address = '0x0000000000000000000000000000000000000000'

nectar_token = bind_contract(
    nectar_token_address,
    os.path.join('..', 'truffle', 'build', 'contracts', 'NectarToken.json')
)

bounty_registry = bind_contract(
    bounty_registry_address,
    os.path.join('..', 'truffle', 'build', 'contracts', 'BountyRegistry.json')
)

def wait_for_receipt(tx):
    while True:
        receipt = web3.eth.getTransactionReceipt(tx)
        if receipt:
            return receipt
        sleep(1)

def check_transaction(tx):
    receipt = wait_for_receipt(tx)
    return receipt.status == 1

def bounty_fee():
    return 62500000000000000

def assertion_fee():
    return 62500000000000000

def bounty_amount_min():
    return 62500000000000000

def assertion_bid_min():
    return 62500000000000000
