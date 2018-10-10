import logging
import os
import jsonschema
import uuid

from ethereum.utils import sha3
from flask import Blueprint, g, request
from jsonschema.exceptions import ValidationError

from polyswarmd import eth
from polyswarmd.artifacts import is_valid_ipfshash, list_artifacts
from polyswarmd.chains import chain
from polyswarmd.bloom import BloomFilter, FILTER_BITS
from polyswarmd.eth import build_transaction, zero_address
from polyswarmd.response import success, failure
from polyswarmd.utils import bool_list_to_int, bounty_to_dict, assertion_to_dict

logger = logging.getLogger(__name__)  # Init logger
bounties = Blueprint('bounties', __name__)


def calculate_bloom(artifacts):
    bf = BloomFilter()
    for _, h in artifacts:
        bf.add(h.encode('utf-8'))

    v = int(bf)
    ret = []
    d = (1 << 256) - 1
    for _ in range(FILTER_BITS // 256):
        ret.insert(0, v % d)
        v //= d

    return ret


def int_to_bytes(i):
    h = hex(i)[2:]
    return bytes.fromhex('0' * (64 - len(h)) + h)


def int_from_bytes(b):
    return int.from_bytes(b, byteorder='big')


def calculate_commitment(account, verdicts):
    nonce = os.urandom(32)
    account = int(account, 16)
    commitment = sha3(int_to_bytes(verdicts ^ int_from_bytes(sha3(nonce)) ^ account))
    return int_from_bytes(nonce), int_from_bytes(commitment)


@bounties.route('', methods=['POST'])
@chain
def post_bounties():
    account = g.web3.toChecksumAddress(g.eth_address)

    base_nonce = int(
        request.args.get('base_nonce', g.web3.eth.getTransactionCount(account)))

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

    if amount < eth.bounty_amount_min(g.bounty_registry):
        return failure('Invalid bounty amount', 400)

    if not is_valid_ipfshash(artifactURI):
        return failure('Invalid artifact URI (should be IPFS hash)', 400)

    arts = list_artifacts(artifactURI)
    if not arts:
        return failure('Invalid artifact URI (could not retrieve artifacts)',
                       400)

    numArtifacts = len(arts)
    bloom = calculate_bloom(arts)

    approveAmount = amount + eth.bounty_fee(g.bounty_registry)

    transactions = [
        build_transaction(
            g.nectar_token.functions.approve(g.bounty_registry.address,
                                           approveAmount), base_nonce),
        build_transaction(
            g.bounty_registry.functions.postBounty(
                guid.int, amount, artifactURI, numArtifacts, durationBlocks,
                bloom), base_nonce + 1),
    ]

    return success({'transactions': transactions})


@bounties.route('/parameters', methods=['GET'])
@chain
def get_bounty_parameters():
    bounty_fee = g.bounty_registry.functions.BOUNTY_FEE().call()
    assertion_fee = g.bounty_registry.functions.ASSERTION_FEE().call()
    bounty_amount_minimum = g.bounty_registry.functions.BOUNTY_AMOUNT_MINIMUM().call()
    assertion_bid_minimum = g.bounty_registry.functions.ASSERTION_BID_MINIMUM().call()
    arbiter_lookback_range = g.bounty_registry.functions.ARBITER_LOOKBACK_RANGE().call()
    max_duration = g.bounty_registry.functions.MAX_DURATION().call()
    assertion_reveal_window = g.bounty_registry.functions.ASSERTION_REVEAL_WINDOW().call()
    arbiter_vote_window = g.bounty_registry.functions.arbiterVoteWindow().call()

    return success({
        'bounty_fee': bounty_fee,
        'assertion_fee': assertion_fee,
        'bounty_amount_minimum': bounty_amount_minimum,
        'assertion_bid_minimum': assertion_bid_minimum,
        'arbiter_lookback_range': arbiter_lookback_range,
        'max_duration': max_duration,
        'assertion_reveal_window': assertion_reveal_window,
        'arbiter_vote_window':arbiter_vote_window
    })

@bounties.route('/<uuid:guid>', methods=['GET'])
@chain
def get_bounties_guid(guid):
    bounty = bounty_to_dict(
        g.bounty_registry.functions.bountiesByGuid(guid.int).call())
    if not is_valid_ipfshash(bounty['uri']):
        return failure('Invalid IPFS hash in URI', 400)
    if bounty['author'] == zero_address:
        return failure('Bounty not found', 404)

    return success(bounty)


@bounties.route('/<uuid:guid>/vote', methods=['POST'])
@chain
def post_bounties_guid_vote(guid):
    account = g.web3.toChecksumAddress(g.eth_address)

    base_nonce = int(
        request.args.get('base_nonce', g.web3.eth.getTransactionCount(account)))

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

    transactions = [
        build_transaction(
            g.bounty_registry.functions.voteOnBounty(
                guid.int, verdicts, valid_bloom), base_nonce),
    ]
    return success({'transactions': transactions})


@bounties.route('/<uuid:guid>/settle', methods=['POST'])
@chain
def post_bounties_guid_settle(guid):
    account = g.web3.toChecksumAddress(g.eth_address)

    base_nonce = int(
        request.args.get('base_nonce', g.web3.eth.getTransactionCount(account)))

    transactions = [
        build_transaction(
            g.bounty_registry.functions.settleBounty(guid.int), base_nonce)
    ]

    return success({'transactions': transactions})


@bounties.route('/<uuid:guid>/assertions', methods=['POST'])
@chain
def post_bounties_guid_assertions(guid):
    account = g.web3.toChecksumAddress(g.eth_address)

    base_nonce = int(
        request.args.get('base_nonce', g.web3.eth.getTransactionCount(account)))

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

    if bid < eth.assertion_bid_min(g.bounty_registry):
        return failure('Invalid assertion bid', 400)

    nonce, commitment = calculate_commitment(account, verdicts)
    approveAmount = bid + eth.assertion_fee(g.bounty_registry)

    transactions = [
        build_transaction(
            g.nectar_token.functions.approve(g.bounty_registry.address,
                                           approveAmount), base_nonce),
        build_transaction(
            g.bounty_registry.functions.postAssertion(
                guid.int, bid, mask, commitment), base_nonce + 1),
    ]

    # Pass generated nonce onto user in response, used for reveal
    return success({'transactions': transactions, 'nonce': str(nonce)})


@bounties.route('/<uuid:guid>/assertions/<int:id_>/reveal', methods=['POST'])
@chain
def post_bounties_guid_assertions_id_reveal(guid, id_):
    account = g.web3.toChecksumAddress(g.eth_address)

    base_nonce = int(
        request.args.get('base_nonce', g.web3.eth.getTransactionCount(account)))

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

    transactions = [
        build_transaction(
            g.bounty_registry.functions.revealAssertion(
                guid.int, id_, nonce, verdicts, metadata), base_nonce),
    ]
    return success({'transactions': transactions})


@bounties.route('/<uuid:guid>/assertions', methods=['GET'])
@chain
def get_bounties_guid_assertions(guid):
    bounty = bounty_to_dict(
        g.bounty_registry.functions.bountiesByGuid(guid.int).call())
    num_assertions = g.bounty_registry.functions.getNumberOfAssertions(
        guid.int).call()
    assertions = []
    for i in range(num_assertions):
        assertion = assertion_to_dict(
            g.bounty_registry.functions.assertionsByGuid(guid.int, i).call(),
                bounty['num_artifacts'])
        assertions.append(assertion)

    return success(assertions)


@bounties.route('/<uuid:guid>/assertions/<int:id_>', methods=['GET'])
@chain
def get_bounties_guid_assertions_id(guid, id_):
    try:
        return success(
            assertion_to_dict(
                g.bounty_registry.functions.assertionsByGuid(guid.int,
                                                           id_).call()))
    except:
        return failure('Assertion not found', 404)
