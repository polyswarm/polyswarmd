import os
import jsonschema
import uuid

from ethereum.utils import sha3
from flask import Blueprint, request
from jsonschema.exceptions import ValidationError

from polyswarmd import eth
from polyswarmd.artifacts import is_valid_ipfshash, list_artifacts
from polyswarmd.bloom import BloomFilter, FILTER_BITS
from polyswarmd.eth import web3 as web3_chains, build_transaction, nectar_token as nectar_chains, bounty_registry as bounty_chains, zero_address
from polyswarmd.response import success, failure
from polyswarmd.utils import bool_list_to_int, bounty_to_dict, assertion_to_dict

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
    h = hex(i)[2:]
    return bytes.fromhex('0' * (64 - len(h)) + h)


def int_from_bytes(b):
    return int.from_bytes(b, byteorder='big')


def calculate_commitment(verdicts):
    nonce = os.urandom(32)
    commitment = sha3(int_to_bytes(verdicts ^ int_from_bytes(sha3(nonce))))
    return int_from_bytes(nonce), int_from_bytes(commitment)


@bounties.route('', methods=['POST'])
def post_bounties():
    # Must read chain before account to have a valid web3 ref
    chain = request.args.get('chain', 'home')
    if chain != 'side' and chain != 'home':
        return failure('Chain must be either home or side', 400)

    web3 = web3_chains[chain]
    nectar_token = nectar_chains[chain]
    bounty_registry = bounty_chains[chain]

    account = request.args.get('account')
    if not account or not web3.isAddress(account):
        return failure('Source account required', 401)
    account = web3.toChecksumAddress(account)

    base_nonce = int(
        request.args.get('base_nonce', web3.eth.getTransactionCount(account)))

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

    transactions = [
        build_transaction(
            nectar_token.functions.approve(bounty_registry.address,
                                           approveAmount), chain, base_nonce),
        build_transaction(
            bounty_registry.functions.postBounty(
                guid.int, amount, artifactURI, numArtifacts, durationBlocks,
                bloom), chain, base_nonce + 1),
    ]

    return success({'transactions': transactions})


# TODO: Caching layer for this
@bounties.route('', methods=['GET'])
def get_bounties():
    chain = request.args.get('chain', 'home')
    if chain != 'side' and chain != 'home':
        return failure('Chain must be either home or side', 400)

    bounty_registry = bounty_chains[chain]

    num_bounties = bounty_registry.functions.getNumberOfBounties().call()
    ret = []
    for i in range(num_bounties):
        guid = bounty_registry.functions.bountyGuids(i).call()
        bounty = bounty_to_dict(
            bounty_registry.functions.bountiesByGuid(guid).call())
        if not is_valid_ipfshash(bounty['uri']):
            continue

        ret.append(bounty)

    return success(ret)


# TODO: Caching layer for this
@bounties.route('/active', methods=['GET'])
def get_bounties_active():
    chain = request.args.get('chain', 'home')
    if chain != 'side' and chain != 'home':
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

        if not is_valid_ipfshash(bounty['uri']):
            continue

        if bounty['expiration'] > current_block:
            ret.append(bounty)

    return success(ret)


# TODO: Caching layer for this
# Gets bounties that have been revealed and have not been voted on
@bounties.route('/pending', methods=['GET'])
def get_bounties_pending():
    chain = request.args.get('chain', 'home')
    if chain != 'side' and chain != 'home':
        return failure('Chain must be either home or side', 400)

    web3 = web3_chains[chain]
    bounty_registry = bounty_chains[chain]

    current_block = web3.eth.blockNumber
    num_bounties = bounty_registry.functions.getNumberOfBounties().call()
    assertion_reveal_window = bounty_registry.functions.ASSERTION_REVEAL_WINDOW().call()

    ret = []
    for i in range(num_bounties):
        guid = bounty_registry.functions.bountyGuids(i).call()
        bounty = bounty_to_dict(
            bounty_registry.functions.bountiesByGuid(guid).call())

        if not is_valid_ipfshash(bounty['uri']):
            continue
        if bounty['expiration'] + int(assertion_reveal_window) <= current_block and not bounty['resolved']:
            ret.append(bounty)

    return success(ret)


@bounties.route('/<uuid:guid>', methods=['GET'])
def get_bounties_guid(guid):
    chain = request.args.get('chain', 'home')
    if chain != 'side' and chain != 'home':
        return failure('Chain must be either home or side', 400)

    bounty_registry = bounty_chains[chain]

    bounty = bounty_to_dict(
        bounty_registry.functions.bountiesByGuid(guid.int).call())
    if not is_valid_ipfshash(bounty['uri']):
        return failure('Invalid IPFS hash in URI', 400)
    if bounty['author'] == zero_address:
        return failure('Bounty not found', 404)

    return success(bounty)


@bounties.route('/<uuid:guid>/vote', methods=['POST'])
def post_bounties_guid_vote(guid):
    chain = request.args.get('chain', 'home')
    if chain != 'side' and chain != 'home':
        return failure('Chain must be either home or side', 400)

    web3 = web3_chains[chain]
    bounty_registry = bounty_chains[chain]

    account = request.args.get('account')
    if not account or not web3.isAddress(account):
        return failure('Source account required', 401)
    account = web3.toChecksumAddress(account)

    base_nonce = int(
        request.args.get('base_nonce', web3.eth.getTransactionCount(account)))

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
            bounty_registry.functions.voteOnBounty(
                guid.int, verdicts, valid_bloom), chain, base_nonce),
    ]
    return success({'transactions': transactions})


@bounties.route('/<uuid:guid>/settle', methods=['POST'])
def post_bounties_guid_settle(guid):
    chain = request.args.get('chain', 'home')
    if chain != 'side' and chain != 'home':
        return failure('Chain must be either home or side', 400)

    web3 = web3_chains[chain]
    bounty_registry = bounty_chains[chain]

    account = request.args.get('account')
    if not account or not web3.isAddress(account):
        return failure('Source account required', 401)
    account = web3.toChecksumAddress(account)

    base_nonce = int(
        request.args.get('base_nonce', web3.eth.getTransactionCount(account)))

    transactions = [
        build_transaction(
            bounty_registry.functions.settleBounty(guid.int), chain,
            base_nonce),
    ]
    return success({'transactions': transactions})


@bounties.route('/<uuid:guid>/assertions', methods=['POST'])
def post_bounties_guid_assertions(guid):
    chain = request.args.get('chain', 'home')
    if chain != 'side' and chain != 'home':
        return failure('Chain must be either home or side', 400)

    web3 = web3_chains[chain]
    nectar_token = nectar_chains[chain]
    bounty_registry = bounty_chains[chain]

    account = request.args.get('account')
    if not account or not web3.isAddress(account):
        return failure('Source account required', 401)
    account = web3.toChecksumAddress(account)

    base_nonce = int(
        request.args.get('base_nonce', web3.eth.getTransactionCount(account)))

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

    if bid < eth.assertion_bid_min():
        return failure('Invalid assertion bid', 400)

    nonce, commitment = calculate_commitment(verdicts)
    approveAmount = bid + eth.assertion_fee()

    transactions = [
        build_transaction(
            nectar_token.functions.approve(bounty_registry.address,
                                           approveAmount), chain, base_nonce),
        build_transaction(
            bounty_registry.functions.postAssertion(
                guid.int, bid, mask, commitment), chain, base_nonce + 1),
    ]

    # Pass generated nonce onto user in response, used for reveal
    return success({'transactions': transactions, 'nonce': str(nonce)})


@bounties.route('/<uuid:guid>/assertions/<int:id_>/reveal', methods=['POST'])
def post_bounties_guid_assertions_id_reveal(guid, id_):
    chain = request.args.get('chain', 'home')
    if chain != 'side' and chain != 'home':
        return failure('Chain must be either home or side', 400)

    web3 = web3_chains[chain]
    nectar_token = nectar_chains[chain]
    bounty_registry = bounty_chains[chain]

    account = request.args.get('account')
    if not account or not web3.isAddress(account):
        return failure('Source account required', 401)
    account = web3.toChecksumAddress(account)

    base_nonce = int(
        request.args.get('base_nonce', web3.eth.getTransactionCount(account)))

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
            bounty_registry.functions.revealAssertion(
                guid.int, id_, nonce, verdicts, metadata), chain, base_nonce),
    ]
    return success({'transactions': transactions})


@bounties.route('/<uuid:guid>/assertions', methods=['GET'])
def get_bounties_guid_assertions(guid):
    chain = request.args.get('chain', 'home')
    if chain != 'side' and chain != 'home':
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
    chain = request.args.get('chain', 'home')
    if chain != 'side' and chain != 'home':
        return failure('Chain must be either home or side', 400)

    bounty_registry = bounty_chains[chain]

    try:
        return success(
            assertion_to_dict(
                bounty_registry.functions.assertionsByGuid(guid.int,
                                                           id_).call()))
    except:
        return failure('Assertion not found', 404)
