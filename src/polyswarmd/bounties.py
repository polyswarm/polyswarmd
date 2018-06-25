import os
import uuid

import jsonschema

from ethereum.utils import sha3
from flask import Blueprint, request
from jsonschema.exceptions import ValidationError

from polyswarmd import eth
from polyswarmd.artifacts import is_valid_ipfshash, list_artifacts
from polyswarmd.bloom import BloomFilter, FILTER_BITS
from polyswarmd.eth import web3 as web3_chains, check_transaction, nectar_token as nectar_chains, bounty_registry as bounty_chains, zero_address
from polyswarmd.response import success, failure
from polyswarmd.websockets import transaction_queue as transaction_chains
from polyswarmd.utils import bool_list_to_int, bounty_to_dict, assertion_to_dict, new_bounty_event_to_dict, \
        new_assertion_event_to_dict, new_verdict_event_to_dict, revealed_assertion_event_to_dict

bounties = Blueprint('bounties', __name__)


def calculate_bloom(arts):
    bf = BloomFilter()
    for _, h in arts:
        bf.add(h.encode('utf-8'))

    v = int(bf)
    ret = []
    d = (1 << 256) - 1
    for _ in range(FILTER_BITS // 256):
        ret.insert(0, v % d)
        v //= d

    return ret


def int_to_bytes(i):
    return bytes.fromhex(hex(i)[2:])


def int_from_bytes(b):
    return int.from_bytes(b, byteorder='big')


def calculate_commitment(verdicts):
    nonce = os.urandom(32)
    commitment = sha3(int_to_bytes(verdicts ^ int_from_bytes(sha3(nonce))))
    return int_from_bytes(nonce), int_from_bytes(commitment)


@bounties.route('', methods=['POST'])
def post_bounties():
    # Must read chain before account to have a valid web3 ref
    chain = request.args.get('chain')
    if not chain:
        chain = 'home'
    elif chain != 'side' and chain != 'home':
        return failure('Chain must be either home or side', 400)

    transaction_queue = transaction_chains[chain]
    web3 = web3_chains[chain]
    nectar_token = nectar_chains[chain]
    bounty_registry = bounty_chains[chain]

    account = request.args.get('account')
    if not account or not web3.isAddress(account):
        return failure('Source account required', 401)
    account = web3.toChecksumAddress(account)

    schema = {
        'type': 'object',
        'properties': {
            'amount': {
                'type': 'string',
                'minLength': 1,
                'maxLength': 100,
                'pattern': r'^\d+$',
            },
            'uri': {
                'type': 'string',
                'minLength': 1,
                'maxLength': 100,
            },
            'duration': {
                'type': 'integer',
                'minimum': 1,
            },
            'base_nonce': {
                'type': 'integer',
                'minimum': 0,
            }
        },
        'required': ['amount', 'uri', 'duration'],
    }

    body = request.get_json()
    try:
        jsonschema.validate(body, schema)
    except ValidationError as e:
        return failure('Invalid JSON: ' + e.message, 400)

    guid = uuid.uuid4()
    amount = int(body['amount'])
    artifactURI = body['uri']
    durationBlocks = body['duration']

    if amount < eth.bounty_amount_min():
        return failure('Invalid bounty amount', 400)

    if not is_valid_ipfshash(artifactURI):
        return failure('Invalid artifact URI (should be IPFS hash)', 400)

    arts = list_artifacts(artifactURI)
    if not arts:
        return failure('Invalid artifact URI (could not retrieve artifacts)',
                       400)

    numArtifacts = len(arts)
    bloom = calculate_bloom(arts)

    approveAmount = amount + eth.bounty_fee()

    if 'base_nonce' in body:
        base_nonce = body['base_nonce']
    else:
        base_nonce = web3.eth.getTransactionCount(account)

    tx = transaction_queue.send_transaction(
        nectar_token.functions.approve(bounty_registry.address, approveAmount),
        account, base_nonce).get()
    if not check_transaction(web3, tx):
        return failure(
            'Approve transaction failed, verify parameters and try again', 400)

    base_nonce += 1;

    tx = transaction_queue.send_transaction(
        bounty_registry.functions.postBounty(guid.int, amount, artifactURI,
                                             numArtifacts, durationBlocks,
                                             bloom), account, base_nonce).get()
    if not check_transaction(web3, tx):
        return failure(
            'Post bounty transaction failed, verify parameters and try again',
            400)
    receipt = web3.eth.getTransactionReceipt(tx)
    processed = bounty_registry.events.NewBounty().processReceipt(receipt)
    if not processed:
        return failure(
            'Invalid transaction receipt, no events emitted. Check contract addresses',
            400)
    new_bounty_event = processed[0]['args']
    return success(new_bounty_event_to_dict(new_bounty_event))


# TODO: Caching layer for this
@bounties.route('', methods=['GET'])
def get_bounties():
    chain = request.args.get('chain')
    if not chain:
        chain = 'home'
    elif chain != 'side' and chain != 'home':
        return failure('Chain must be either home or side', 400)

    bounty_registry = bounty_chains[chain]

    num_bounties = bounty_registry.functions.getNumberOfBounties().call()
    ret = []
    for i in range(num_bounties):
        guid = bounty_registry.functions.bountyGuids(i).call()
        ret.append(
            bounty_to_dict(
                bounty_registry.functions.bountiesByGuid(guid).call()))

    return success(ret)


# TODO: Caching layer for this
@bounties.route('/active', methods=['GET'])
def get_bounties_active():
    chain = request.args.get('chain')
    if not chain:
        chain = 'home'
    elif chain != 'side' and chain != 'home':
        return failure('Chain must be either home or side', 400)

    web3 = web3_chains[chain]
    bounty_registry = bounty_chains[chain]

    current_block = web3.eth.blockNumber
    num_bounties = bounty_registry.functions.getNumberOfBounties().call()
    ret = []
    for i in range(num_bounties):
        guid = bounty_registry.functions.bountyGuids(i).call()
        bounty = bounty_to_dict(
            bounty_registry.functions.bountiesByGuid(guid).call())

        if bounty['expiration'] > current_block:
            ret.append(bounty)

    return success(ret)


# TODO: Caching layer for this
@bounties.route('/pending', methods=['GET'])
def get_bounties_pending():
    chain = request.args.get('chain')
    if not chain:
        chain = 'home'
    elif chain != 'side' and chain != 'home':
        return failure('Chain must be either home or side', 400)

    web3 = web3_chains[chain]
    bounty_registry = bounty_chains[chain]

    current_block = web3.eth.blockNumber
    num_bounties = bounty_registry.functions.getNumberOfBounties().call()
    ret = []
    for i in range(num_bounties):
        guid = bounty_registry.functions.bountyGuids(i).call()
        bounty = bounty_to_dict(
            bounty_registry.functions.bountiesByGuid(guid).call())

        if bounty['expiration'] <= current_block and not bounty['resolved']:
            ret.append(bounty)

    return success(ret)


@bounties.route('/<uuid:guid>', methods=['GET'])
def get_bounties_guid(guid):
    chain = request.args.get('chain')
    if not chain:
        chain = 'home'
    elif chain != 'side' and chain != 'home':
        return failure('Chain must be either home or side', 400)

    bounty_registry = bounty_chains[chain]

    bounty = bounty_to_dict(
        bounty_registry.functions.bountiesByGuid(guid.int).call())
    if bounty['author'] == zero_address:
        return failure('Bounty not found', 404)

    return success(bounty)


@bounties.route('/<uuid:guid>/vote', methods=['POST'])
def post_bounties_guid_vote(guid):
    chain = request.args.get('chain')
    if not chain:
        chain = 'home'
    elif chain != 'side' and chain != 'home':
        return failure('Chain must be either home or side', 400)

    web3 = web3_chains[chain]
    transaction_queue = transaction_chains[chain]
    bounty_registry = bounty_chains[chain]

    account = request.args.get('account')
    if not account or not web3.isAddress(account):
        return failure('Source account required', 401)
    account = web3.toChecksumAddress(account)

    schema = {
        'type': 'object',
        'properties': {
            'verdicts': {
                'type': 'array',
                'maxItems': 256,
                'items': {
                    'type': 'boolean',
                },
            },
            'valid_bloom': {
                'type': 'boolean',
            },
            'base_nonce': {
                'type': 'integer',
                'minimum': 0,
            }
        },
        'required': ['verdicts', 'valid_bloom'],
    }

    body = request.get_json()
    try:
        jsonschema.validate(body, schema)
    except ValidationError as e:
        return failure('Invalid JSON: ' + e.message, 400)

    verdicts = bool_list_to_int(body['verdicts'])
    valid_bloom = bool(body['valid_bloom'])

    if 'base_nonce' in body:
        base_nonce = body['base_nonce']
    else:
        base_nonce = web3.eth.getTransactionCount(account)

    tx = transaction_queue.send_transaction(
        bounty_registry.functions.voteOnBounty(guid.int, verdicts,
                                               valid_bloom), account, base_nonce).get()
    if not check_transaction(web3, tx):
        return failure(
            'Settle bounty transaction failed, verify parameters and try again',
            400)

    receipt = web3.eth.getTransactionReceipt(tx)
    processed = bounty_registry.events.NewVerdict().processReceipt(receipt)
    if not processed:
        return failure(
            'Invalid transaction receipt, no events emitted. Check contract addresses',
            400)
    new_verdict_event = processed[0]['args']
    return success(new_verdict_event_to_dict(new_verdict_event))


@bounties.route('/<uuid:guid>/settle', methods=['POST'])
def post_bounties_guid_settle(guid):
    chain = request.args.get('chain')
    if not chain:
        chain = 'home'
    elif chain != 'side' and chain != 'home':
        return failure('Chain must be either home or side', 400)

    web3 = web3_chains[chain]
    transaction_queue = transaction_chains[chain]
    bounty_registry = bounty_chains[chain]

    account = request.args.get('account')
    if not account or not web3.isAddress(account):
        return failure('Source account required', 401)
    account = web3.toChecksumAddress(account)
    if 'base_nonce' in body:
        base_nonce = body['base_nonce']
    else:
        base_nonce = web3.eth.getTransactionCount(account)

    tx = transaction_queue.send_transaction(
        bounty_registry.functions.settleBounty(guid.int), account, base_nonce).get()
    if not check_transaction(web3, tx):
        return failure(
            'Settle bounty transaction failed, verify parameters and try again',
            400)

    # TODO: raise event in contract?
    return success()


@bounties.route('/<uuid:guid>/assertions', methods=['POST'])
def post_bounties_guid_assertions(guid):
    chain = request.args.get('chain')
    if not chain:
        chain = 'home'
    elif chain != 'side' and chain != 'home':
        return failure('Chain must be either home or side', 400)

    web3 = web3_chains[chain]
    nectar_token = nectar_chains[chain]
    transaction_queue = transaction_chains[chain]
    bounty_registry = bounty_chains[chain]

    account = request.args.get('account')
    if not account or not web3.isAddress(account):
        return failure('Source account required', 401)
    account = web3.toChecksumAddress(account)

    schema = {
        'type': 'object',
        'properties': {
            'bid': {
                'type': 'string',
                'minLength': 1,
                'maxLength': 100,
                'pattern': r'^\d+$',
            },
            'mask': {
                'type': 'array',
                'maxItems': 256,
                'items': {
                    'type': 'boolean',
                },
            },
            'verdicts': {
                'type': 'array',
                'maxItems': 256,
                'items': {
                    'type': 'boolean',
                },
            },
            'base_nonce': {
                'type': 'integer',
                'minimum': 0,
            }
        },
        'required': ['bid', 'mask', 'verdicts'],
    }

    body = request.get_json()
    try:
        jsonschema.validate(body, schema)
    except ValidationError as e:
        return failure('Invalid JSON: ' + e.message, 400)

    bid = int(body['bid'])
    mask = bool_list_to_int(body['mask'])
    verdicts = bool_list_to_int(body['verdicts'])

    if bid < eth.assertion_bid_min():
        return failure('Invalid assertion bid', 400)

    nonce, commitment = calculate_commitment(verdicts)
    approveAmount = bid + eth.assertion_fee()
    if 'base_nonce' in body:
        base_nonce = body['base_nonce']
    else:
        base_nonce = web3.eth.getTransactionCount(account)

    tx = transaction_queue.send_transaction(
        nectar_token.functions.approve(bounty_registry.address, approveAmount),
        account, base_nonce).get()
    if not check_transaction(web3, tx):
        return failure(
            'Approve transaction failed, verify parameters and try again', 400)

    base_nonce += 1;

    tx = transaction_queue.send_transaction(
        bounty_registry.functions.postAssertion(guid.int, bid, mask,
                                                commitment), account, base_nonce).get()
    if not check_transaction(web3, tx):
        return failure(
            'Post assertion transaction failed, verify parameters and try again',
            400)

    receipt = web3.eth.getTransactionReceipt(tx)
    processed = bounty_registry.events.NewAssertion().processReceipt(receipt)
    if not processed:
        return failure(
            'Invalid transaction receipt, no events emitted. Check contract addresses',
            400)
    new_assertion_event = processed[0]['args']

    # Pass generated nonce onto user in response, used for reveal
    ret = new_assertion_event_to_dict(new_assertion_event)
    ret['nonce'] = str(nonce)
    return success(ret)


@bounties.route('/<uuid:guid>/assertions/<int:id_>/reveal', methods=['POST'])
def post_bounties_guid_assertions_id_reveal(guid, id_):
    chain = request.args.get('chain')
    if not chain:
        chain = 'home'
    elif chain != 'side' and chain != 'home':
        return failure('Chain must be either home or side', 400)

    web3 = web3_chains[chain]
    nectar_token = nectar_chains[chain]
    transaction_queue = transaction_chains[chain]
    bounty_registry = bounty_chains[chain]

    account = request.args.get('account')
    if not account or not web3.isAddress(account):
        return failure('Source account required', 401)
    account = web3.toChecksumAddress(account)

    schema = {
        'type': 'object',
        'properties': {
            'nonce': {
                'type': 'string',
                'minLength': 1,
                'maxLength': 100,
                'pattern': r'^\d+$',
            },
            'verdicts': {
                'type': 'array',
                'maxItems': 256,
                'items': {
                    'type': 'boolean',
                },
            },
            'metadata': {
                'type': 'string',
                'maxLength': 1024,
            },
            'base_nonce': {
                'type': 'integer',
                'minimum': 0,
            }
        },
        'required': ['nonce', 'verdicts', 'metadata'],
    }

    body = request.get_json()
    try:
        jsonschema.validate(body, schema)
    except ValidationError as e:
        return failure('Invalid JSON: ' + e.message, 400)

    nonce = int(body['nonce'])
    verdicts = bool_list_to_int(body['verdicts'])
    metadata = body['metadata']

    if 'base_nonce' in body:
        base_nonce = body['base_nonce']
    else:
        base_nonce = web3.eth.getTransactionCount(account)

    tx = transaction_queue.send_transaction(
        bounty_registry.functions.revealAssertion(
            guid.int, id_, nonce, verdicts, metadata), account, base_nonce).get()
    if not check_transaction(web3, tx):
        return failure(
            'Reveal assertion transaction failed, verify parameters and try again',
            400)

    receipt = web3.eth.getTransactionReceipt(tx)
    processed = bounty_registry.events.RevealedAssertion().processReceipt(
        receipt)
    if not processed:
        return failure(
            'Invalid transaction receipt, no events emitted. Check contract addresses',
            400)
    revealed_assertion_event = processed[0]['args']
    return success(revealed_assertion_event_to_dict(revealed_assertion_event))


@bounties.route('/<uuid:guid>/assertions', methods=['GET'])
def get_bounties_guid_assertions(guid):
    chain = request.args.get('chain')
    if not chain:
        chain = 'home'
    elif chain != 'side' and chain != 'home':
        return failure('Chain must be either home or side', 400)

    bounty_registry = bounty_chains[chain]

    num_assertions = bounty_registry.functions.getNumberOfAssertions(
        guid.int).call()
    assertions = []
    for i in range(num_assertions):
        assertion = assertion_to_dict(
            bounty_registry.functions.assertionsByGuid(guid.int, i).call())
        assertions.append(assertion)

    return success(assertions)


@bounties.route('/<uuid:guid>/assertions/<int:id_>', methods=['GET'])
def get_bounties_guid_assertions_id(guid, id_):
    chain = request.args.get('chain')
    if not chain:
        chain = 'home'
    elif chain != 'side' and chain != 'home':
        return failure('Chain must be either home or side', 400)

    bounty_registry = bounty_chains[chain]

    try:
        return success(
            assertion_to_dict(
                bounty_registry.functions.assertionsByGuid(guid.int,
                                                           id_).call()))
    except:
        return failure('Assertion not found', 404)
