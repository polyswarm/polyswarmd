import json
import logging
import os
import jsonschema
import uuid

from ethereum.utils import sha3
from flask import Blueprint, g, request
from jsonschema.exceptions import ValidationError
from polyswarmartifact import ArtifactType
from polyswarmartifact.schema import Assertion as AssertionMetadata, Bounty as BountyMetadata

from polyswarmd import eth, cache
from polyswarmd.artifacts import is_valid_ipfshash, list_artifacts, post_to_ipfs, get_from_ipfs
from polyswarmd.chains import chain
from polyswarmd.bloom import BloomFilter, FILTER_BITS
from polyswarmd.eth import build_transaction, ZERO_ADDRESS
from polyswarmd.response import success, failure
from polyswarmd.utils import bool_list_to_int, bounty_to_dict, assertion_to_dict, vote_to_dict, bloom_to_dict

logger = logging.getLogger(__name__)
bounties = Blueprint('bounties', __name__)


def calculate_bloom(artifacts):
    bf = BloomFilter()
    for _, h, _ in artifacts:
        bf.add(h.encode('utf-8'))

    v = int(bf)
    ret = []
    d = (1 << 256)
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


@cache.memoize(30)
def substitute_ipfs_metadata(ipfs_uri, validate=AssertionMetadata.validate, ipfs_root=None, session=None):
    """Download metadata from IPFS and validate it against the schema.

    :param ipfs_uri: Potential IPFS uri string
    :param validate: Function that takes a loaded json blob and returns true if it matches the schema
    :param ipfs_root: Root uri for ipfs
    :param session: Requests session for ipfs request
    :return: Metadata from IPFS, or original metadata
    """
    if not is_valid_ipfshash(ipfs_uri):
        return ipfs_uri

    status_code, content = get_from_ipfs(ipfs_uri, ipfs_root=ipfs_root, session=session)
    try:
        if status_code // 100 == 2 and validate(json.loads(content.decode('utf-8'))):
            return json.loads(content.decode('utf-8'))
    except json.JSONDecodeError:
        # Expected when people provide incorrect metadata. Not stack worthy
        logger.warning('Metadata retrieved from IPFS does not match schema')
    except Exception:
        logger.exception('Error getting metadata from IPFS')

    return ipfs_uri


@bounties.route('', methods=['POST'])
@chain
def post_bounties():
    account = g.chain.w3.toChecksumAddress(g.eth_address)
    base_nonce = int(request.args.get('base_nonce', g.chain.w3.eth.getTransactionCount(account)))

    schema = {
        'type': 'object',
        'properties': {
            'artifact_type': {
                'type': 'string',
                'enum': [name.lower() for name, value in ArtifactType.__members__.items()]
            },
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
            'metadata': {
                'type': 'string',
                'minLength': 1,
                'maxLength': 100,
            }
        },
        'required': ['artifact_type', 'amount', 'uri', 'duration'],
    }

    body = request.get_json()
    try:
        jsonschema.validate(body, schema)
    except ValidationError as e:
        return failure('Invalid JSON: ' + e.message, 400)

    guid = uuid.uuid4()
    artifact_type = ArtifactType.from_string(body['artifact_type'])
    amount = int(body['amount'])
    artifact_uri = body['uri']
    duration_blocks = body['duration']
    metadata = body.get('metadata', '')

    if amount < eth.bounty_amount_min(g.chain.bounty_registry.contract):
        return failure('Invalid bounty amount', 400)

    if not is_valid_ipfshash(artifact_uri):
        return failure('Invalid artifact URI (should be IPFS hash)', 400)

    if metadata and not is_valid_ipfshash(metadata):
        return failure('Invalid bounty metadata URI (should be IPFS hash)', 400)

    arts = list_artifacts(artifact_uri)
    if not arts:
        return failure('Invalid artifact URI (could not retrieve artifacts)',
                       400)

    num_artifacts = len(arts)
    bloom = calculate_bloom(arts)

    approve_amount = amount + eth.bounty_fee(g.chain.bounty_registry.contract)

    transactions = [
        build_transaction(
            g.chain.nectar_token.contract.functions.approve(g.chain.bounty_registry.contract.address, approve_amount),
            base_nonce),
        build_transaction(
            g.chain.bounty_registry.contract.functions.postBounty(guid.int, artifact_type.value, amount, artifact_uri,
                                                                  num_artifacts, duration_blocks, bloom, metadata),
            base_nonce + 1),
    ]

    return success({'transactions': transactions})


@bounties.route('/parameters', methods=['GET'])
@cache.memoize(1)
@chain
def get_bounty_parameters():
    bounty_fee = g.chain.bounty_registry.contract.functions.bountyFee().call()
    assertion_fee = g.chain.bounty_registry.contract.functions.assertionFee().call()
    bounty_amount_minimum = g.chain.bounty_registry.contract.functions.BOUNTY_AMOUNT_MINIMUM().call()
    assertion_bid_minimum = g.chain.bounty_registry.contract.functions.ASSERTION_BID_MINIMUM().call()
    arbiter_lookback_range = g.chain.bounty_registry.contract.functions.ARBITER_LOOKBACK_RANGE().call()
    max_duration = g.chain.bounty_registry.contract.functions.MAX_DURATION().call()
    assertion_reveal_window = g.chain.bounty_registry.contract.functions.ASSERTION_REVEAL_WINDOW().call()
    arbiter_vote_window = g.chain.bounty_registry.contract.functions.arbiterVoteWindow().call()

    return success({
        'bounty_fee': bounty_fee,
        'assertion_fee': assertion_fee,
        'bounty_amount_minimum': bounty_amount_minimum,
        'assertion_bid_minimum': assertion_bid_minimum,
        'arbiter_lookback_range': arbiter_lookback_range,
        'max_duration': max_duration,
        'assertion_reveal_window': assertion_reveal_window,
        'arbiter_vote_window': arbiter_vote_window
    })


@bounties.route('/<uuid:guid>', methods=['GET'])
@cache.memoize(1)
@chain
def get_bounties_guid(guid):
    bounty = bounty_to_dict(
        g.chain.bounty_registry.contract.functions.bountiesByGuid(guid.int).call())
    metadata = bounty.get('metadata', None)
    if metadata:
        metadata = substitute_ipfs_metadata(metadata, validate=BountyMetadata.validate)
    else:
        metadata = None
    bounty['metadata'] = metadata
    if not is_valid_ipfshash(bounty['uri']):
        return failure('Invalid IPFS hash in URI', 400)
    if bounty['author'] == ZERO_ADDRESS:
        return failure('Bounty not found', 404)

    return success(bounty)


@bounties.route('/<uuid:guid>/vote', methods=['POST'])
@chain
def post_bounties_guid_vote(guid):
    account = g.chain.w3.toChecksumAddress(g.eth_address)
    base_nonce = int(request.args.get('base_nonce', g.chain.w3.eth.getTransactionCount(account)))

    schema = {
        'type': 'object',
        'properties': {
            'votes': {
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
        'required': ['votes', 'valid_bloom'],
    }

    body = request.get_json()
    try:
        jsonschema.validate(body, schema)
    except ValidationError as e:
        return failure('Invalid JSON: ' + e.message, 400)

    votes = bool_list_to_int(body['votes'])
    valid_bloom = bool(body['valid_bloom'])

    transactions = [
        build_transaction(g.chain.bounty_registry.contract.functions.voteOnBounty(guid.int, votes, valid_bloom),
                          base_nonce),
    ]
    return success({'transactions': transactions})


@bounties.route('/<uuid:guid>/settle', methods=['POST'])
@chain
def post_bounties_guid_settle(guid):
    account = g.chain.w3.toChecksumAddress(g.eth_address)
    base_nonce = int(request.args.get('base_nonce', g.chain.w3.eth.getTransactionCount(account)))

    transactions = [
        build_transaction(g.chain.bounty_registry.contract.functions.settleBounty(guid.int), base_nonce)
    ]

    return success({'transactions': transactions})


@bounties.route('/metadata', methods=['POST'])
def post_assertion_metadata():
    body = request.get_json()

    loaded_body = json.loads(body)
    try:
        if not AssertionMetadata.validate(loaded_body, silent=True) and \
                not BountyMetadata.validate(loaded_body, silent=True):
            return failure('Invalid metadata', 400)
    except json.JSONDecodeError:
        # Expected when people provide incorrect metadata. Not stack worthy
        return failure('Invalid Assertion metadata', 400)

    try:
        status_code, ipfshash = post_to_ipfs([('metadata', body)], wrap_dir=False)
        return success(ipfshash) if status_code // 100 == 2 else failure('Could not add metadata to IPFS', status_code)
    except Exception:
        logger.exception('Received error posting to IPFS got response')
        return failure('Could not add metadata to ipfs', 400)


@bounties.route('/<uuid:guid>/assertions', methods=['POST'])
@chain
def post_bounties_guid_assertions(guid):
    account = g.chain.w3.toChecksumAddress(g.eth_address)
    base_nonce = int(request.args.get('base_nonce', g.chain.w3.eth.getTransactionCount(account)))

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
            'commitment': {
                'type': 'string',
                'minLength': 1,
                'maxLength': 100,
                'pattern': r'^\d+$',
            },
        },
        'required': ['bid', 'mask'],
    }

    body = request.get_json()
    try:
        jsonschema.validate(body, schema)
    except ValidationError as e:
        return failure('Invalid JSON: ' + e.message, 400)

    bid = int(body['bid'])
    mask = bool_list_to_int(body['mask'])

    commitment = body.get('commitment')
    verdicts = body.get('verdicts')

    if commitment is None and verdicts is None:
        return failure('Require verdicts or a commitment', 400)

    if bid < eth.assertion_bid_min(g.chain.bounty_registry.contract):
        return failure('Invalid assertion bid', 400)

    approveAmount = bid + eth.assertion_fee(g.chain.bounty_registry.contract)

    nonce = None
    if commitment is None:
        nonce, commitment = calculate_commitment(account, bool_list_to_int(verdicts))
    else:
        commitment = int(commitment)

    ret = {'transactions': [
        build_transaction(
            g.chain.nectar_token.contract.functions.approve(g.chain.bounty_registry.contract.address,
                                                            approveAmount), base_nonce),
        build_transaction(g.chain.bounty_registry.contract.functions.postAssertion(guid.int, bid, mask, commitment),
                          base_nonce + 1),
    ]}

    if nonce is not None:
        # Pass generated nonce onto user in response, used for reveal
        ret['nonce'] = nonce

    return success(ret)


@bounties.route('/<uuid:guid>/assertions/<int:id_>/reveal', methods=['POST'])
@chain
def post_bounties_guid_assertions_id_reveal(guid, id_):
    account = g.chain.w3.toChecksumAddress(g.eth_address)
    base_nonce = int(request.args.get('base_nonce', g.chain.w3.eth.getTransactionCount(account)))

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
            g.chain.bounty_registry.contract.functions.revealAssertion(guid.int, id_, nonce, verdicts, metadata),
            base_nonce),
    ]
    return success({'transactions': transactions})


@bounties.route('/<uuid:guid>/assertions', methods=['GET'])
@cache.memoize(1)
@chain
def get_bounties_guid_assertions(guid):
    bounty = bounty_to_dict(g.chain.bounty_registry.contract.functions.bountiesByGuid(guid.int).call())
    if bounty['author'] == ZERO_ADDRESS:
        return failure('Bounty not found', 404)

    num_assertions = g.chain.bounty_registry.contract.functions.getNumberOfAssertions(guid.int).call()

    assertions = []
    for i in range(num_assertions):
        try:
            assertion = assertion_to_dict(
                g.chain.bounty_registry.contract.functions.assertionsByGuid(guid.int, i).call(),
                bounty['num_artifacts'])
            assertion['metadata'] = substitute_ipfs_metadata(assertion.get('metadata', ''))
            assertions.append(assertion)
        except Exception:
            logger.exception('Could not retrieve assertion')
            continue

    return success(assertions)


@bounties.route('/<uuid:guid>/assertions/<int:id_>', methods=['GET'])
@cache.memoize(1)
@chain
def get_bounties_guid_assertions_id(guid, id_):
    bounty = bounty_to_dict(g.chain.bounty_registry.contract.functions.bountiesByGuid(guid.int).call())
    if bounty['author'] == ZERO_ADDRESS:
        return failure('Bounty not found', 404)

    try:
        assertion = assertion_to_dict(g.chain.bounty_registry.contract.functions.assertionsByGuid(guid.int, id_).call(),
                                      bounty['num_artifacts'])
        assertion['metadata'] = substitute_ipfs_metadata(assertion.get('metadata', ''))

        return success(assertion)
    except:
        return failure('Assertion not found', 404)


@bounties.route('/<uuid:guid>/votes', methods=['GET'])
@cache.memoize(1)
@chain
def get_bounties_guid_votes(guid):
    bounty = bounty_to_dict(g.chain.bounty_registry.contract.functions.bountiesByGuid(guid.int).call())
    if bounty['author'] == ZERO_ADDRESS:
        return failure('Bounty not found', 404)

    num_votes = g.chain.bounty_registry.contract.functions.getNumberOfVotes(guid.int).call()

    votes = []
    for i in range(num_votes):
        try:
            vote = vote_to_dict(
                g.chain.bounty_registry.contract.functions.votesByGuid(guid.int, i).call(),
                bounty['num_artifacts'])
            votes.append(vote)
        except Exception:
            logger.exception('Could not retrieve vote')
            continue

    return success(votes)


@bounties.route('/<uuid:guid>/votes/<int:id_>', methods=['GET'])
@cache.memoize(1)
@chain
def get_bounties_guid_votes_id(guid, id_):
    bounty = bounty_to_dict(g.chain.bounty_registry.contract.functions.bountiesByGuid(guid.int).call())
    if bounty['author'] == ZERO_ADDRESS:
        return failure('Bounty not found', 404)

    try:
        vote = vote_to_dict(g.chain.bounty_registry.contract.functions.votesByGuid(guid.int, id_).call(),
                            bounty['num_artifacts'])
        return success(vote)
    except:
        return failure('Vote not found', 404)


@bounties.route('/<uuid:guid>/bloom', methods=['GET'])
@cache.memoize(30)
@chain
def get_bounties_guid_bloom(guid):
    bounty = bounty_to_dict(g.chain.bounty_registry.contract.functions.bountiesByGuid(guid.int).call())
    if bounty['author'] == ZERO_ADDRESS:
        return failure('Bounty not found', 404)

    try:
        bloom_parts = []
        for i in range(0, 8):
            bloom_parts.append(g.chain.bounty_registry.contract.functions.bloomByGuid(guid.int, i).call())
        bloom = bloom_to_dict(bloom_parts)
        return success(bloom)
    except:
        logger.exception('Bloom not found')
        return failure('Bloom not found', 404)
