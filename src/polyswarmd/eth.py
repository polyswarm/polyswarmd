import json
import jsonschema
import os
import rlp

from collections import defaultdict
from ethereum.transactions import Transaction
from flask import Blueprint, request
from hexbytes import HexBytes
from jsonschema.exceptions import ValidationError
from web3 import Web3, HTTPProvider
from web3.middleware import geth_poa_middleware

from polyswarmd.artifacts import is_valid_ipfshash
from polyswarmd.config import config_location, chain_id, eth_uri, nectar_token_address, bounty_registry_address, offer_registry_address, whereami
from polyswarmd.response import success, failure

misc = Blueprint('misc', __name__)


def bind_contract(web3_, address, artifact):
    with open(os.path.abspath(os.path.join(whereami(), artifact)), 'r') as f:
        abi = json.load(f)['abi']

    return web3_.eth.contract(
        address=web3_.toChecksumAddress(address), abi=abi)


gas_limit = 500000,  # TODO: not sure if this should be hardcoded/fixed; min gas needed for POST to /offers
zero_address = '0x0000000000000000000000000000000000000000'

offer_msig_artifact = os.path.join(config_location, 'contracts',
                                   'OfferMultiSig.json')

web3 = {}

# Create token bindings for each chain
bounty_registry = {}
nectar_token = {}

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

    if chain is 'home':
        offer_registry = bind_contract(
            web3[chain], offer_registry_address[chain],
            os.path.join(config_location, 'contracts', 'OfferRegistry.json'))

        offer_lib_address = offer_registry.functions.offerLib().call()

        offer_lib = bind_contract(web3[chain], offer_lib_address,
                                  os.path.join(config_location, 'contracts',
                                               'OfferLib.json'))
 
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

    account = request.args.get('account')
    if not account or not w3.isAddress(account):
        return failure('Source account required', 401)
    account = w3.toChecksumAddress(account)

    return success(w3.eth.getTransactionCount(account))


@misc.route('/transactions', methods=['POST'])
def post_transactions():
    # Must read chain before account to have a valid web3 ref
    chain = request.args.get('chain', 'home')
    if chain != 'side' and chain != 'home':
        return failure('Chain must be either home or side', 400)

    w3 = web3[chain]

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

        # TODO: Additional validation (addresses, methods, etc)

        txhashes.append(w3.eth.sendRawTransaction(HexBytes(raw_tx)))

    ret = defaultdict(list)
    for txhash in txhashes:
        events = events_from_transaction(txhash, chain)
        for k, v in events.items():
            ret[k].extend(v)

    return success(ret)


def build_transaction(call, chain, nonce):
    return call.buildTransaction({
        'nonce': nonce,
        'chainId': int(chain_id[chain]),
        'gas': gas_limit,
    })


def events_from_transaction(txhash, chain):
    from polyswarmd.utils import new_bounty_event_to_dict, new_assertion_event_to_dict, \
            new_verdict_event_to_dict, revealed_assertion_event_to_dict, \
            transfer_event_to_dict

    # TODO: Check for out of gas, other
    # TODO: Report contract errors
    receipt = web3[chain].eth.getTransactionReceipt(txhash)
    if not receipt:
        return {'errors': {txhash: 'transaction receipt not available'}}
    if receipt.gasUsed == gas_limit:
        return {'errors': {txhash: 'transaction ran out of gas'}}
    if receipt.status != 1:
        return {'errors': {txhash: 'transaction failed, check parameters'}}

    ret = {}

    # Transfers
    processed = nectar_token[
        chain].events.Transfer().processReceipt(receipt)
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

    # Offers
    # TODO: no conversion functions for most of these, do we want those?
    offer_msig = bind_contract(web3, zero_address, offer_msig_artifact)

    processed = offer_registry.events.InitializedChannel().processReceipt(
        receipt)
    if processed:
        initialized = dict(processed[0]['args'])
        ret['offers_initialized'] = ret.get('offers_initialized', []) + [initialized]

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
        ret['offers_challenged'] = ret.get('offers_challenged', []) + [challenged]

    return ret

def bounty_fee():
    return 62500000000000000


def assertion_fee():
    return 62500000000000000


def bounty_amount_min():
    return 62500000000000000


def assertion_bid_min():
    return 62500000000000000
