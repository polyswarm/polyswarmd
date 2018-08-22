import json
import jsonschema
import logging
import os
import rlp

from collections import defaultdict
from ethereum.transactions import Transaction
from flask import Blueprint, g, request
from hexbytes import HexBytes
from jsonschema.exceptions import ValidationError
from web3 import Web3, HTTPProvider
from web3.middleware import geth_poa_middleware

from polyswarmd.artifacts import is_valid_ipfshash
from polyswarmd.config import config_location, chain_id, eth_uri, nectar_token_address, bounty_registry_address, offer_registry_address, whereami, free
from polyswarmd.response import success, failure

misc = Blueprint('misc', __name__)


def bind_contract(web3_, address, artifact):
    with open(os.path.abspath(os.path.join(whereami(), artifact)), 'r') as f:
        abi = json.load(f)['abi']

    return web3_.eth.contract(
        address=web3_.toChecksumAddress(address), abi=abi)


<<<<<<< HEAD
gas_limit = 5000000  # TODO: not sure if this should be hardcoded/fixed; min gas needed for POST to settle bounty
=======
gas_limit = 7000000 # TODO: not sure if this should be hardcoded/fixed; min gas needed for POST to settle bounty
>>>>>>> fix messages
zero_address = '0x0000000000000000000000000000000000000000'

offer_msig_artifact = os.path.join(config_location, 'contracts',
                                   'OfferMultiSig.json')

web3 = {}

# Create token bindings for each chain
bounty_registry = {}
nectar_token = {}
arbiter_staking = {}

# exists only on home
offer_registry = None
offer_lib = None

for chain in ('home', 'side'):
    temp = Web3(HTTPProvider(eth_uri[chain]))
    temp.middleware_stack.inject(geth_poa_middleware, layer=0)
    web3[chain] = temp
    nectar_token[chain] = bind_contract(
        web3[chain], nectar_token_address[chain],
        os.path.join(config_location, 'contracts', 'NectarToken.json'))

    bounty_registry[chain] = bind_contract(
        web3[chain], bounty_registry_address[chain],
        os.path.join(config_location, 'contracts', 'BountyRegistry.json'))
    arbiter_staking[chain] = bind_contract(
        web3[chain], bounty_registry[chain].functions.staking().call(),
        os.path.join(config_location, 'contracts', 'ArbiterStaking.json'))

    if chain == 'home':
        offer_registry = bind_contract(
            web3[chain], offer_registry_address[chain],
            os.path.join(config_location, 'contracts', 'OfferRegistry.json'))

        offer_lib_address = offer_registry.functions.offerLib().call()

        offer_lib = bind_contract(
            web3[chain], offer_lib_address,
            os.path.join(config_location, 'contracts', 'OfferLib.json'))


@misc.route('/syncing', methods=['GET'])
def get_syncing():
    # Must read chain before account to have a valid web3 ref
    chain = request.args.get('chain')
    if not chain:
        chain = 'home'
    elif chain != 'side' and chain != 'home':
        return failure('Chain must be either home or side', 400)

    w3 = web3[chain]

    if not w3.eth.syncing:
        return success(False)

    return success(dict(w3.eth.syncing))


@misc.route('/nonce', methods=['GET'])
def get_nonce():
    # Must read chain before account to have a valid web3 ref
    chain = request.args.get('chain')
    if not chain:
        chain = 'home'
    elif chain != 'side' and chain != 'home':
        return failure('Chain must be either home or side', 400)

    w3 = web3[chain]
    account = w3.toChecksumAddress(g.eth_address)

    return success(w3.eth.getTransactionCount(account))


@misc.route('/transactions', methods=['POST'])
def post_transactions():
    # Must read chain before account to have a valid web3 ref
    chain = request.args.get('chain', 'home')
    if chain != 'side' and chain != 'home':
        return failure('Chain must be either home or side', 400)

    w3 = web3[chain]
    account = w3.toChecksumAddress(g.eth_address)

    schema = {
        'type': 'object',
        'properties': {
            'transactions': {
                'type': 'array',
                'items': {
                    'type': 'string',
                    'minLength': 1,
                    'maxLength': 4096,
                    'pattern': r'^[0-9a-fA-F]+$',
                }
            },
        },
        'required': ['transactions'],
    }

    body = request.get_json()
    try:
        jsonschema.validate(body, schema)
    except ValidationError as e:
        return failure('Invalid JSON: ' + e.message, 400)

    txhashes = []
    for raw_tx in body['transactions']:
        try:
            tx = rlp.decode(bytes.fromhex(raw_tx), Transaction)
        except:
            continue

        sender = w3.toChecksumAddress(tx.sender.hex())
        if sender != account:
            logging.warning(
                'Got invalid transaction sender, expected %s got %s', account,
                sender)
            continue

        # TODO: Additional validation (addresses, methods, etc)

        txhashes.append(w3.eth.sendRawTransaction(HexBytes(raw_tx)))

    ret = defaultdict(list)
    for txhash in txhashes:
        events = events_from_transaction(txhash, chain)
        for k, v in events.items():
            ret[k].extend(v)

    
    print(ret)
    print(txhashes)
    return success(ret)


def build_transaction(call, chain, nonce):
    options = {
        'nonce': nonce,
        'chainId': int(chain_id[chain]),
        'gas': gas_limit,
    }
    if free[chain]:
        options["gasPrice"] = 0
    return call.buildTransaction(options)


def events_from_transaction(txhash, chain):
    from polyswarmd.utils import new_bounty_event_to_dict, new_assertion_event_to_dict, \
            new_verdict_event_to_dict, revealed_assertion_event_to_dict, \
            transfer_event_to_dict, new_withdrawal_event_to_dict, new_deposit_event_to_dict

    # TODO: Check for out of gas, other
    # TODO: Report contract errors
    receipt = web3[chain].eth.waitForTransactionReceipt(txhash)
    txhash = bytes(txhash).hex()
    if not receipt:
        return {
            'errors':
            ['transaction {0}: receipt not available'.format(txhash)]
        }
    if receipt.gasUsed == gas_limit:
        return {'errors': ['transaction {0}: out of gas'.format(txhash)]}
    if receipt.status != 1:
        return {
            'errors': [
                'transaction {0}: transaction failed, check parameters'.format(
                    txhash)
            ]
        }

    ret = {}

    # Transfers
    processed = nectar_token[chain].events.Transfer().processReceipt(receipt)
    if processed:
        transfer = transfer_event_to_dict(processed[0]['args'])
        ret['transfers'] = ret.get('transfers', []) + [transfer]

    # Bounties
    processed = bounty_registry[chain].events.NewBounty().processReceipt(
        receipt)
    if processed:
        bounty = new_bounty_event_to_dict(processed[0]['args'])

        if is_valid_ipfshash(bounty['uri']):
            ret['bounties'] = ret.get('bounties', []) + [bounty]

    processed = bounty_registry[chain].events.NewAssertion().processReceipt(
        receipt)
    if processed:
        assertion = new_assertion_event_to_dict(processed[0]['args'])
        ret['assertions'] = ret.get('assertions', []) + [assertion]

    processed = bounty_registry[chain].events.NewVerdict().processReceipt(
        receipt)
    if processed:
        verdict = new_verdict_event_to_dict(processed[0]['args'])
        ret['verdicts'] = ret.get('verdicts', []) + [verdict]

    processed = bounty_registry[
        chain].events.RevealedAssertion().processReceipt(receipt)
    if processed:
        reveal = revealed_assertion_event_to_dict(processed[0]['args'])
        ret['reveals'] = ret.get('reveals', []) + [reveal]

    # Arbiter
    processed = arbiter_staking[chain].events.NewWithdrawal().processReceipt(
        receipt)
    if processed:
        withdrawal = new_withdrawal_event_to_dict(processed[0]['args'])
        ret['withdrawals'] = ret.get('withdrawals', []) + [withdrawal]

    processed = arbiter_staking[chain].events.NewDeposit().processReceipt(
        receipt)
    if processed:
        deposit = new_deposit_event_to_dict(processed[0]['args'])
        ret['deposits'] = ret.get('deposits', []) + [deposit]

    # Offers
    # TODO: no conversion functions for most of these, do we want those?
    offer_msig = bind_contract(web3['home'], zero_address, offer_msig_artifact)

    processed = offer_registry.events.InitializedChannel().processReceipt(
        receipt)
    if processed:
        initialized = dict(processed[0]['args'])
        ret['offers_initialized'] = ret.get('offers_initialized',
                                            []) + [initialized]

    processed = offer_msig.events.OpenedAgreement().processReceipt(receipt)
    if processed:
        opened = dict(processed[0]['args'])
        ret['offers_opened'] = ret.get('offers_opened', []) + [opened]

    processed = offer_msig.events.CanceledAgreement().processReceipt(receipt)
    if processed:
        canceled = dict(processed[0]['args'])
        ret['offers_canceled'] = ret.get('offers_canceled', []) + [canceled]

    processed = offer_msig.events.JoinedAgreement().processReceipt(receipt)
    if processed:
        joined = dict(processed[0]['args'])
        ret['offers_joined'] = ret.get('offers_joined', []) + [joined]

    processed = offer_msig.events.ClosedAgreement().processReceipt(receipt)
    if processed:
        closed = dict(processed[0]['args'])
        ret['offers_closed'] = ret.get('offers_closed', []) + [closed]

    processed = offer_msig.events.StartedSettle().processReceipt(receipt)
    if processed:
        settled = dict(processed[0]['args'])
        ret['offers_settled'] = ret.get('offers_settled', []) + [settled]

    processed = offer_msig.events.SettleStateChallenged().processReceipt(
        receipt)
    if processed:
        challenged = dict(processed[0]['args'])
        ret['offers_challenged'] = ret.get('offers_challenged',
                                           []) + [challenged]

    return ret


def bounty_fee(chain):
    return bounty_registry[chain].functions.BOUNTY_FEE().call()


def assertion_fee(chain):
    return bounty_registry[chain].functions.ASSERTION_FEE().call()


def bounty_amount_min(chain):
    return bounty_registry[chain].functions.BOUNTY_AMOUNT_MINIMUM().call()


def assertion_bid_min(chain):
    return bounty_registry[chain].functions.ASSERTION_BID_MINIMUM().call()


def staking_total_max(chain):
    return arbiter_staking[chain].functions.MAXIMUM_STAKE().call()


def staking_total_min(chain):
    return arbiter_staking[chain].functions.MINIMUM_STAKE().call()
