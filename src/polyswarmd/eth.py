import gevent
import json
import jsonschema
import logging
import os
import rlp
import functools

from collections import defaultdict
from ethereum.transactions import Transaction
from flask import Blueprint, g, request
from hexbytes import HexBytes
from jsonschema.exceptions import ValidationError
from web3 import Web3, HTTPProvider

from polyswarmd.artifacts import is_valid_ipfshash
from polyswarmd.config import config_location, whereami
from polyswarmd.response import success, failure

logger = logging.getLogger(__name__)  # Init logger
misc = Blueprint('misc', __name__)


def bind_contract(web3_, address, artifact):
    with open(os.path.abspath(os.path.join(whereami(), artifact)), 'r') as f:
        abi = json.load(f)['abi']

    return web3_.eth.contract(
        address=web3_.toChecksumAddress(address), abi=abi)


gas_limit = 5000000  # TODO: not sure if this should be hardcoded/fixed; min gas needed for POST to settle bounty

zero_address = '0x0000000000000000000000000000000000000000'

offer_msig_artifact = os.path.join(config_location, 'contracts',
                                   'OfferMultiSig.json')

from polyswarmd.chains import chain


@misc.route('/syncing', methods=['GET'])
@chain
def get_syncing():
    if not g.web3.eth.syncing:
        return success(False)

    return success(dict(g.web3.eth.syncing))


@misc.route('/nonce', methods=['GET'])
@chain
def get_nonce():
    account = g.web3.toChecksumAddress(g.eth_address)

    return success(g.web3.eth.getTransactionCount(account))


@misc.route('/transactions', methods=['POST'])
@chain
def post_transactions():
    account = g.web3.toChecksumAddress(g.eth_address)

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

    errors = []
    txhashes = []
    for raw_tx in body['transactions']:
        try:
            tx = rlp.decode(bytes.fromhex(raw_tx), Transaction)
        except:
            continue

        sender = g.web3.toChecksumAddress(tx.sender.hex())
        if sender != account:
            errors.append('Invalid transaction sender for tx {0}: expected {1} got {2}'.format(tx.hash.hex(), account, sender))
            continue

        # TODO: Additional validation (addresses, methods, etc)
        try:
            txhashes.append(g.web3.eth.sendRawTransaction(HexBytes(raw_tx)))
        except ValueError as e:
            errors.append('Invalid transaction error for tx {0}: {1}'.format(tx.hash.hex(), e))

    ret = defaultdict(list)
    ret['errors'].extend(errors)
    for txhash in txhashes:
        events = events_from_transaction(txhash)
        for k, v in events.items():
            ret[k].extend(v)

    if ret['errors']:
        logging.exception('Got transaction errors: %s', ret['errors'])
        return failure(ret, 400)

    return success(ret)


def build_transaction(call, nonce):
    options = {
        'nonce': nonce,
        'chainId': int(g.chain_id),
        'gas': gas_limit,
    }
    if g.free:
        options["gasPrice"] = 0

    return call.buildTransaction(options)


def events_from_transaction(txhash):
    from polyswarmd.utils import new_bounty_event_to_dict, new_assertion_event_to_dict, \
        new_verdict_event_to_dict, revealed_assertion_event_to_dict, \
        transfer_event_to_dict, new_withdrawal_event_to_dict, new_deposit_event_to_dict

    # TODO: Check for out of gas, other
    # TODO: Report contract errors
    timeout = gevent.Timeout(60)
    timeout.start()
    try:
        with gevent.Timeout(60, Exception('Timeout waiting for transaction receipt')) as timeout:
            while True:
                receipt = g.web3.eth.getTransactionReceipt(txhash)
                if receipt is not None:
                    break
                gevent.sleep(0.1)
        while True:
            receipt = g.web3.eth.getTransactionReceipt(txhash)
            if receipt is not None:
                break
            gevent.sleep(0.1)
    except gevent.Timeout as t:
        if t is not timeout:
            raise
        logging.exception('Transaction %s: timeout waiting for receipt', bytes(txhash).hex())
        return {
            'errors':
                ['transaction {0}: exception occurred during wait for receipt'.format(bytes(txhash).hex())]
        }
    except Exception:
        logger.exception('Transaction %s: error while fetching transaction receipt', bytes(txhash).hex())
        return {
            'errors':
                ['transaction {0}: unhandled error while fetching transaction receipt'.format(bytes(txhash).hex())]
        }
    finally:
        timeout.cancel()

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
                'transaction {0}: transaction failed at block {1}, check parameters'.format(
                    txhash, receipt.blockNumber)
            ]
        }

    ret = {}

    # Transfers
    processed = g.nectar_token.events.Transfer().processReceipt(receipt)
    if processed:
        transfer = transfer_event_to_dict(processed[0]['args'])
        ret['transfers'] = ret.get('transfers', []) + [transfer]

    # Bounties
    processed = g.bounty_registry.events.NewBounty().processReceipt(
        receipt)
    if processed:
        bounty = new_bounty_event_to_dict(processed[0]['args'])

        if is_valid_ipfshash(bounty['uri']):
            ret['bounties'] = ret.get('bounties', []) + [bounty]

    processed = g.bounty_registry.events.NewAssertion().processReceipt(
        receipt)
    if processed:
        assertion = new_assertion_event_to_dict(processed[0]['args'])
        ret['assertions'] = ret.get('assertions', []) + [assertion]

    processed = g.bounty_registry.events.NewVerdict().processReceipt(
        receipt)
    if processed:
        verdict = new_verdict_event_to_dict(processed[0]['args'])
        ret['verdicts'] = ret.get('verdicts', []) + [verdict]

    processed = g.bounty_registry.events.RevealedAssertion().processReceipt(receipt)
    if processed:
        reveal = revealed_assertion_event_to_dict(processed[0]['args'])
        ret['reveals'] = ret.get('reveals', []) + [reveal]

    # Arbiter
    processed = g.arbiter_staking.events.NewWithdrawal().processReceipt(
        receipt)
    if processed:
        withdrawal = new_withdrawal_event_to_dict(processed[0]['args'])
        ret['withdrawals'] = ret.get('withdrawals', []) + [withdrawal]

    processed = g.arbiter_staking.events.NewDeposit().processReceipt(
        receipt)
    if processed:
        deposit = new_deposit_event_to_dict(processed[0]['args'])
        ret['deposits'] = ret.get('deposits', []) + [deposit]

    # Offers
    # TODO: no conversion functions for most of these, do we want those?
    if g.offer_registry is None:
        return ret

    offer_msig = bind_contract(g.web3, zero_address, offer_msig_artifact)
    processed = g.offer_registry.events.InitializedChannel().processReceipt(
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


def bounty_fee(bounty_registry):
    return bounty_registry.functions.BOUNTY_FEE().call()


def assertion_fee(bounty_registry):
    return bounty_registry.functions.ASSERTION_FEE().call()


def bounty_amount_min(bounty_registry):
    return bounty_registry.functions.BOUNTY_AMOUNT_MINIMUM().call()


def assertion_bid_min(bounty_registry):
    return bounty_registry.functions.ASSERTION_BID_MINIMUM().call()


def staking_total_max(arbiter_staking):
    return arbiter_staking.functions.MAXIMUM_STAKE().call()


def staking_total_min(arbiter_staking):
    return arbiter_staking.functions.MINIMUM_STAKE().call()
