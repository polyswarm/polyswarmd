import gevent
import jsonschema
import logging
import rlp

from collections import defaultdict
from eth_abi import decode_abi
from eth_abi.exceptions import InsufficientDataBytes
from eth.vm.forks.constantinople.transactions import (
    ConstantinopleTransaction
)
from flask import current_app as app, Blueprint, g, request
from hexbytes import HexBytes
from jsonschema.exceptions import ValidationError

from polyswarmd import cache
from polyswarmd.chains import chain
from polyswarmd.response import success, failure

from web3.module import Module

logger = logging.getLogger(__name__)

misc = Blueprint('misc', __name__)

MAX_GAS_LIMIT = 50000000
GAS_MULTIPLIER = 1.5
ZERO_ADDRESS = '0x0000000000000000000000000000000000000000'
TRANSFER_SIGNATURE_HASH = 'a9059cbb'
TIMEOUT = 60


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
    if 'ignore_pending' in request.args.keys():
        return success(g.chain.w3.eth.getTransactionCount(account))
    else:
        return success(g.chain.w3.eth.getTransactionCount(account, 'pending'))


@misc.route('/pending', methods=['GET'])
@chain
def get_pending_nonces():
    tx_pool = get_txpool()
    logger.debug('Got txpool response from Ethereum node: %s', tx_pool)
    transactions = dict()
    for key in tx_pool.keys():
        tx_pool_category_nonces = tx_pool[key].get(g.eth_address, {})
        transactions.update(dict(tx_pool_category_nonces))

    nonces = [str(nonce) for nonce in transactions.keys()]
    logger.debug('Pending txpool for %s: %s', g.eth_address, nonces)
    return success(nonces)


@misc.route('/transactions', methods=['GET'])
@chain
def get_transactions():
    schema = {
        'type': 'object',
        'properties': {
            'transactions': {
                'type': 'array',
                'maxItems': 10,
                'items': {
                    'type': 'string',
                    'minLength': 2,
                    'maxLength': 66,
                    'pattern': r'^(0x)?[0-9a-fA-F]{64}$',
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

    ret = defaultdict(list)
    for transaction in body['transactions']:
        event = events_from_transaction(HexBytes(transaction), g.chain.name)
        for k, v in event.items():
            ret[k].extend(v)

    if ret['errors']:
        logging.error('Got transaction errors: %s', ret['errors'])
        return failure(ret, 400)
    return success(ret)


@misc.route('/transactions', methods=['POST'])
@chain
def post_transactions():
    threadpool_executor = app.config['GEVENT_THREADPOOL']
    account = g.chain.w3.toChecksumAddress(g.eth_address)

    # Does not include offer_multisig contracts, need to loosen validation for those
    contract_addresses = {g.chain.w3.toChecksumAddress(c.address) for c in (
        g.chain.nectar_token, g.chain.bounty_registry, g.chain.arbiter_staking, g.chain.erc20_relay,
        g.chain.offer_registry
    ) if c.address is not None}

    schema = {
        'type': 'object',
        'properties': {
            'transactions': {
                'type': 'array',
                'maxItems': 10,
                'items': {
                    'type': 'string',
                    'minLength': 1,
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

    errors = False
    results = []
    decoded_txs = []
    try:
        future = threadpool_executor.submit(decode_all, body['transactions'])
        decoded_txs = future.result()
    except ValueError as e:
        logger.critical('Invalid transaction: %s', e)
        errors = True
        results.append({
            'is_error': True,
            'message': f'Invalid transaction: {e}'
        })
    except Exception:
        logger.exception('Unexpected exception while parsing transaction')
        errors = True
        results.append({
            'is_error': True,
            'message': 'Unexpected exception while parsing transaction'
        })

    for raw_tx, tx in zip(body['transactions'], decoded_txs):
        if withdrawal_only and not is_withdrawal(tx):
            errors = True
            results.append({
                'is_error': True,
                'message': f'Invalid transaction for tx {tx.hash.hex()}: only withdrawals allowed without an API key'
            })
            continue

        sender = g.chain.w3.toChecksumAddress(tx.sender.hex())
        if sender != account:
            errors = True
            results.append({
                'is_error': True,
                'message': f'Invalid transaction sender for tx {tx.hash.hex()}: expected {account} got {sender}'
            })
            continue

        # Redundant check against zero address, but explicitly guard against contract deploys via this route
        to = g.chain.w3.toChecksumAddress(tx.to.hex())
        if to == ZERO_ADDRESS or to not in contract_addresses:
            errors = True
            results.append({
                'is_error': True,
                'message': f'Invalid transaction recipient for tx {tx.hash.hex()}: {to}'
            })
            continue

        logger.info('Sending tx from %s to %s with nonce %s', sender, to, tx.nonce)

        try:
            results.append({
                'is_error': False,
                'message': g.chain.w3.eth.sendRawTransaction(HexBytes(raw_tx)).hex()})
        except ValueError as e:
            errors = True
            results.append({
                'is_error': True,
                'message': f'Invalid transaction error for tx {tx.hash.hex()}: {e}'
            })
    if errors:
        return failure(results, 400)

    return success(results)


@cache.memoize(1)
def get_txpool():
    return g.chain.w3.txpool.inspect


def get_gas_limit():
    gas_limit = MAX_GAS_LIMIT
    if app.config['CHECK_BLOCK_LIMIT']:
        gas_limit = g.chain.w3.eth.getBlock('latest').gasLimit

    if app.config['CHECK_BLOCK_LIMIT'] and gas_limit >= MAX_GAS_LIMIT:
        app.config['CHECK_BLOCK_LIMIT'] = False

    return gas_limit


def build_transaction(call, nonce):
    # Only a problem for fresh chains
    gas_limit = get_gas_limit()
    options = {
        'nonce': nonce,
        'chainId': int(g.chain.chain_id),
        'gas': gas_limit,
    }

    gas = gas_limit
    if g.chain.free:
        options["gasPrice"] = 0
    else:
        try:
            gas = int(call.estimateGas({'from': g.eth_address, **options}) * GAS_MULTIPLIER)
        except ValueError as e:
            logger.debug('Error estimating gas, using default: %s', e)

    options['gas'] = min(gas_limit, gas)
    logger.debug('options: %s', options)

    return call.buildTransaction(options)


def decode_all(raw_txs):
    return [rlp.decode(bytes.fromhex(raw_tx), sedes=ConstantinopleTransaction) for raw_tx in raw_txs]


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
    if (tx.data.startswith(HexBytes(TRANSFER_SIGNATURE_HASH))
            and g.chain.nectar_token.address == to
            and tx.value == 0
            and tx.network_id == app.config["POLYSWARMD"].chains['side'].chain_id
            and target == g.chain.erc20_relay.address
            and amount > 0):
        logger.info('Transaction is a withdrawal by %s for %d NCT', sender, amount)
        return True

    logger.warning('Transaction by %s to %s is not a withdrawal', sender, to)
    return False


def events_from_transaction(txhash, chain):
    from polyswarmd.utils import new_bounty_event_to_dict, new_assertion_event_to_dict, \
        new_vote_event_to_dict, revealed_assertion_event_to_dict, \
        transfer_event_to_dict, new_withdrawal_event_to_dict, new_deposit_event_to_dict

    config = app.config['POLYSWARMD']
    trace_transactions = config.trace_transactions
    if trace_transactions:
        try:
            Debug.attach(g.chain.w3, 'debug')
        except AttributeError:
            # We've already attached, just continue
            pass

    # TODO: Check for out of gas, other
    timeout = gevent.Timeout(seconds=TIMEOUT)
    timeout.start()

    try:
        while True:
            receipt = g.chain.w3.eth.getTransactionReceipt(txhash)
            if receipt is not None:
                break
            gevent.sleep(1)

    except gevent.Timeout as t:
        if t is not timeout:
            raise
        logging.error('Transaction %s: timeout waiting for receipt', bytes(txhash).hex())
        return {
            'errors':
                [f'transaction {bytes(txhash).hex()}: timeout during wait for receipt']
        }
    except Exception:
        logger.exception('Transaction %s: error while fetching transaction receipt', bytes(txhash).hex())
        return {
            'errors':
                [f'transaction {bytes(txhash).hex()}: unexpected error while fetching transaction receipt']
        }
    finally:
        timeout.cancel()

    txhash = bytes(txhash).hex()
    if not receipt:
        return {
            'errors':
                [f'transaction {txhash}: receipt not available']
        }
    if receipt.gasUsed == MAX_GAS_LIMIT:
        return {'errors': [f'transaction {txhash}: out of gas']}
    if receipt.status != 1:
        if trace_transactions:
            error = g.chain.w3.debug.getTransactionError(txhash)
            logger.error('Transaction %s failed with error message: %s', txhash, error)
            return {
                'errors': [
                    f'transaction {txhash}: transaction failed at block {receipt.blockNumber}, error: {error}'
                ]
            }
        else:
            return {
                'errors': [
                    f'transaction {txhash}: transaction failed at block {receipt.blockNumber}, check parameters'
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

        if config.artifact_client.check_uri(bounty['uri']):
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

    offer_msig = g.chain.offer_multisig.bind(ZERO_ADDRESS)
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


@cache.memoize(1)
def bounty_fee(bounty_registry):
    return bounty_registry.functions.bountyFee().call()


@cache.memoize(1)
def assertion_fee(bounty_registry):
    return bounty_registry.functions.assertionFee().call()


@cache.memoize(1)
def bounty_amount_min(bounty_registry):
    return bounty_registry.functions.BOUNTY_AMOUNT_MINIMUM().call()


@cache.memoize(1)
def assertion_bid_min(bounty_registry):
    return bounty_registry.functions.ASSERTION_BID_ARTIFACT_MINIMUM().call()

@cache.memoize(1)
def assertion_bid_max(bounty_registry):
    return bounty_registry.functions.ASSERTION_BID_ARTIFACT_MAXIMUM().call()


@cache.memoize(1)
def staking_total_max(arbiter_staking):
    return arbiter_staking.functions.MAXIMUM_STAKE().call()


@cache.memoize(1)
def staking_total_min(arbiter_staking):
    return arbiter_staking.functions.MINIMUM_STAKE().call()
