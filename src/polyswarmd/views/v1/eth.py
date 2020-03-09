import fastjsonschema
import logging

from collections import defaultdict
from flask import Blueprint
from flask import current_app as app
from flask import g, request
from hexbytes import HexBytes
from typing import Any, Dict, List

from polyswarmd.utils.decorators.chains import chain
from polyswarmd.utils.eth import events_from_transaction, is_withdrawal, ZERO_ADDRESS, decode_all, get_txpool
from polyswarmd.utils.response import failure, success

logger = logging.getLogger(__name__)

misc: Blueprint = Blueprint('misc', __name__)


@misc.route('/syncing/', methods=['GET'])
@chain
def get_syncing():
    if not g.chain.w3.eth.syncing:
        return success(False)

    return success(dict(g.chain.w3.eth.syncing))


@misc.route('/nonce/', methods=['GET'])
@chain
def get_nonce():
    account = g.chain.w3.toChecksumAddress(g.eth_address)
    if 'ignore_pending' in request.args.keys():
        return success(g.chain.w3.eth.getTransactionCount(account))
    else:
        return success(g.chain.w3.eth.getTransactionCount(account, 'pending'))


@misc.route('/pending/', methods=['GET'])
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


_get_transactions_schema_validator = fastjsonschema.compile({
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
})


@misc.route('/transactions/', methods=['GET'])
@chain
def get_transactions():
    body = request.get_json()
    try:
        _get_transactions_schema_validator(body)
    except fastjsonschema.JsonSchemaException as e:
        return failure('Invalid JSON: ' + e.message, 400)

    ret: Dict[str, List[Any]] = defaultdict(list)
    for transaction in body['transactions']:
        event = events_from_transaction(HexBytes(transaction), g.chain.name)
        for k, v in event.items():
            ret[k].extend(v)

    if ret['errors']:
        logging.error('Got transaction errors: %s', ret['errors'])
        return failure(ret, 400)
    return success(ret)


_post_transactions_schema = fastjsonschema.compile({
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
})


@misc.route('/transactions/', methods=['POST'])
@chain
def post_transactions():
    threadpool_executor = app.config['THREADPOOL']
    account = g.chain.w3.toChecksumAddress(g.eth_address)

    # Does not include offer_multi_sig contracts, need to loosen validation for those
    contract_addresses = {
        g.chain.w3.toChecksumAddress(c.address) for c in (
            g.chain.nectar_token, g.chain.bounty_registry, g.chain.arbiter_staking,
            g.chain.erc20_relay, g.chain.offer_registry
        ) if c.address is not None
    }

    body = request.get_json()
    try:
        _post_transactions_schema(body)
    except fastjsonschema.JsonSchemaException as e:
        return failure('Invalid JSON: ' + e.message, 400)

    withdrawal_only = not g.user and app.config['POLYSWARMD'].auth.require_api_key
    # If we don't have a user key, and they are required, start checking the transaction
    if withdrawal_only and len(body['transactions']) != 1:
        return failure('Posting multiple transactions requires an API key', 403)

    errors = False
    results = []
    decoded_txs = []  # type: Any
    try:
        future = threadpool_executor.submit(decode_all, body['transactions'])
        decoded_txs = future.result()
    except ValueError as e:
        logger.critical('Invalid transaction: %s', e)
        errors = True
        results.append({'is_error': True, 'message': f'Invalid transaction: {e}'})
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
                'is_error':
                    True,
                'message':
                    f'Invalid transaction for tx {tx.hash.hex()}: only withdrawals allowed without an API key'
            })
            continue

        sender = g.chain.w3.toChecksumAddress(tx.sender.hex())
        if sender != account:
            errors = True
            results.append({
                'is_error':
                    True,
                'message':
                    f'Invalid transaction sender for tx {tx.hash.hex()}: expected {account} got {sender}'
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
                'message': g.chain.w3.eth.sendRawTransaction(HexBytes(raw_tx)).hex()
            })
        except ValueError as e:
            errors = True
            results.append({
                'is_error': True,
                'message': f'Invalid transaction error for tx {tx.hash.hex()}: {e}'
            })
    if errors:
        return failure(results, 400)

    return success(results)
