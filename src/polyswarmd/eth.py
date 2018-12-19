import gevent
import jsonschema
import logging
import rlp

from collections import defaultdict
from eth_abi import decode_abi
from eth_abi.exceptions import InsufficientDataBytes
from ethereum.transactions import Transaction
from flask import current_app as app, Blueprint, g, request
from hexbytes import HexBytes
from jsonschema.exceptions import ValidationError

from polyswarmd.artifacts import is_valid_ipfshash
from polyswarmd.chains import chain
from polyswarmd.response import success, failure

from web3.module import Module

logger = logging.getLogger(__name__)

misc = Blueprint('misc', __name__)

# TODO: not sure if this should be hardcoded/fixed; min gas needed for POST to settle bounty
gas_limit = 5000000
zero_address = '0x0000000000000000000000000000000000000000'
transfer_signature_hash = 'a9059cbb'

class Debug(Module):
    ERROR_SELECTOR = '08c379a0'

    def getTransactionError(self, txhash):
        if not txhash.startswith('0x'):
            txhash = '0x' + txhash

        trace = self.web3.manager.request_blocking('debug_traceTransaction', [txhash, {
            'disableStorage': True,
            'disableMemory': True,
            'disableStack': True,
        }])

        if not trace.get('failed'):
            logger.error('Transaction receipt indicates failure but trace succeeded')
            return 'Transaction receipt indicates failure but trace succeeded'

        # Parse out the revert error code if it exists
        # See https://solidity.readthedocs.io/en/v0.4.24/control-structures.html#error-handling-assert-require-revert-and-exceptions
        # Encode as if a function call to `Error(string)`
        rv = HexBytes(trace.get('returnValue'))

        # Trim off function selector for "Error"
        if not rv.startswith(HexBytes(Debug.ERROR_SELECTOR)):
            logger.error('Expected revert encoding to begin with %s, actual is %s', Debug.ERROR_SELECTOR, rv[:4].hex())
            return 'Invalid revert encoding'
        rv = rv[4:]

        error = decode_abi(['string'], rv)[0]
        return error.decode('utf-8')


@misc.route('/syncing', methods=['GET'])
@chain
def get_syncing():
    if not g.chain.w3.eth.syncing:
        return success(False)

    return success(dict(g.chain.w3.eth.syncing))


@misc.route('/nonce', methods=['GET'])
@chain
def get_nonce():
    account = g.chain.w3.toChecksumAddress(g.eth_address)

    return success(g.chain.w3.eth.getTransactionCount(account))


@misc.route('/transactions', methods=['POST'])
@chain
def post_transactions():
    account = g.chain.w3.toChecksumAddress(g.eth_address)

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

    withdrawal_only = not g.user and app.config['POLYSWARMD'].require_api_key
    # If we don't have a user key, and they are required, start checking the transaction
    if withdrawal_only and len(body['transactions']) != 1:
        return failure('Posting multiple transactions requires an API key', 403)

    errors = []
    txhashes = []
    for raw_tx in body['transactions']:
        try:
            tx = rlp.decode(bytes.fromhex(raw_tx), Transaction)
        except ValueError as e:
            logger.error('Invalid transaction: %s', e)
            continue
        except Exception:
            logger.exception('Unexpected exception while parsing transaction')
            continue

        if withdrawal_only and not is_withdrawal(tx):
            errors.append('Invalid transaction for tx {0}: only withdrawals allowed without an API key'.format(tx.hash.hex()))
            continue

        sender = g.chain.w3.toChecksumAddress(tx.sender.hex())
        if sender != account:
            errors.append(
                'Invalid transaction sender for tx {0}: expected {1} got {2}'.format(tx.hash.hex(), account, sender))
            continue

        # TODO: Additional validation (addresses, methods, etc)
        try:
            txhashes.append(g.chain.w3.eth.sendRawTransaction(HexBytes(raw_tx)))
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
        'chainId': int(g.chain.chain_id),
        'gas': gas_limit,
    }
    if g.chain.free:
        options["gasPrice"] = 0

    return call.buildTransaction(options)


def is_withdrawal(tx):
    """
    Take a transaction and return True if that transaction is a withdrawal
    """
    data = tx.data[4:]
    to = g.chain.w3.toChecksumAddress(tx.to.hex())
    sender = g.chain.w3.toChecksumAddress(tx.sender.hex())

    try:
        target, amount = decode_abi(['address', 'uint256'], data)
    except InsufficientDataBytes:
        logger.warning('Transaction by %s to %s is not a withdrawal', sender, to)
        return False

    target = g.chain.w3.toChecksumAddress(target)
    if (
         tx.data.startswith(HexBytes(transfer_signature_hash))
         and g.chain.nectar_token.address == to
         and tx.value == 0
         and tx.network_id == app.config["POLYSWARMD"].chains['side'].chain_id
         and target == g.chain.erc20_relay.address
         and amount > 0):

        logger.info('Transaction is a withdrawal by %s for %d NCT', sender, amount)
        return True

    logger.warning('Transaction by %s to %s is not a withdrawal', sender, to)
    return False


def events_from_transaction(txhash):
    from polyswarmd.utils import new_bounty_event_to_dict, new_assertion_event_to_dict, \
        new_vote_event_to_dict, revealed_assertion_event_to_dict, \
        transfer_event_to_dict, new_withdrawal_event_to_dict, new_deposit_event_to_dict

    trace_transactions = app.config['POLYSWARMD'].trace_transactions
    if trace_transactions:
        try:
            Debug.attach(g.chain.w3, 'debug')
        except AttributeError:
            # We've already attached, just continue
            pass

    # TODO: Check for out of gas, other
    # TODO: Report contract errors
    timeout = gevent.Timeout(300)
    timeout.start()

    try:
        while True:
            receipt = g.chain.w3.eth.getTransactionReceipt(txhash)
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
        if trace_transactions:
            error = g.chain.w3.debug.getTransactionError(txhash)
            logger.error('Transaction %s failed with error message: %s', txhash, error)
            return {
                'errors': [
                    'transaction {0}: transaction failed at block {1}, error: {2}'.format(
                        txhash, receipt.blockNumber, error)
                ]
            }
        else:
            return {
                'errors': [
                    'transaction {0}: transaction failed at block {1}, check parameters'.format(
                        txhash, receipt.blockNumber)
                ]
            }

    ret = {}

    # Transfers
    processed = g.chain.nectar_token.contract.events.Transfer().processReceipt(receipt)
    if processed:
        transfer = transfer_event_to_dict(processed[0]['args'])
        ret['transfers'] = ret.get('transfers', []) + [transfer]

    # Bounties
    processed = g.chain.bounty_registry.contract.events.NewBounty().processReceipt(
        receipt)
    if processed:
        bounty = new_bounty_event_to_dict(processed[0]['args'])

        if is_valid_ipfshash(bounty['uri']):
            ret['bounties'] = ret.get('bounties', []) + [bounty]

    processed = g.chain.bounty_registry.contract.events.NewAssertion().processReceipt(
        receipt)
    if processed:
        assertion = new_assertion_event_to_dict(processed[0]['args'])
        ret['assertions'] = ret.get('assertions', []) + [assertion]

    processed = g.chain.bounty_registry.contract.events.NewVote().processReceipt(
        receipt)
    if processed:
        vote = new_vote_event_to_dict(processed[0]['args'])
        ret['votes'] = ret.get('votes', []) + [vote]

    processed = g.chain.bounty_registry.contract.events.RevealedAssertion().processReceipt(receipt)
    if processed:
        reveal = revealed_assertion_event_to_dict(processed[0]['args'])
        ret['reveals'] = ret.get('reveals', []) + [reveal]

    # Arbiter
    processed = g.chain.arbiter_staking.contract.events.NewWithdrawal().processReceipt(
        receipt)
    if processed:
        withdrawal = new_withdrawal_event_to_dict(processed[0]['args'])
        ret['withdrawals'] = ret.get('withdrawals', []) + [withdrawal]

    processed = g.chain.arbiter_staking.contract.events.NewDeposit().processReceipt(
        receipt)
    if processed:
        deposit = new_deposit_event_to_dict(processed[0]['args'])
        ret['deposits'] = ret.get('deposits', []) + [deposit]

    # Offers
    # TODO: no conversion functions for most of these, do we want those?
    if g.chain.offer_registry.contract is None:
        return ret

    offer_msig = g.chain.offer_multisig.bind(zero_address)
    processed = g.chain.offer_registry.contract.events.InitializedChannel().processReceipt(receipt)
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
