import json
import logging
import os
from typing import List
import uuid

import fastjsonschema
from flask import Blueprint, g, request
from requests import HTTPError

from polyswarmartifact import ArtifactType
from polyswarmartifact.schema import Assertion as AssertionMetadata
from polyswarmartifact.schema import Bounty as BountyMetadata
from polyswarmd import app, cache, eth
from polyswarmd.artifacts.exceptions import ArtifactException
from polyswarmd.bloom import FILTER_BITS, BloomFilter
from polyswarmd.chains import chain
from polyswarmd.eth import ZERO_ADDRESS, build_transaction
from polyswarmd.response import failure, success
from polyswarmd.utils import (
    assertion_to_dict,
    bloom_to_dict,
    bool_list_to_int,
    bounty_to_dict,
    sha3,
    vote_to_dict,
)

MAX_PAGES_PER_REQUEST = 3

logger = logging.getLogger(__name__)
bounties = Blueprint('bounties', __name__)


def calculate_bloom(artifacts):
    bf = BloomFilter()
    for _, h, _ in artifacts:
        bf.add(h.encode('utf-8'))

    v = int(bf)
    ret: List[int] = []
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


def get_assertion(guid, index, num_artifacts):
    config = app.config['POLYSWARMD']
    session = app.config['REQUESTS_SESSION']
    assertion = assertion_to_dict(
        g.chain.bounty_registry.contract.functions.assertionsByGuid(guid.int, index).call(),
        num_artifacts
    )

    bid = [
        str(b) for b in g.chain.bounty_registry.contract.functions.getBids(guid.int, index).call()
    ]
    assertion['bid'] = bid
    assertion['metadata'] = substitute_metadata(
        assertion.get('metadata', ''), config.artifact_client, session, redis=config.redis
    )
    return assertion


@cache.memoize(60)
def get_bounty_guids_page(bounty_registry, page):
    return bounty_registry.functions.getBountyGuids(page).call()


@cache.memoize(60)
def get_page_size(bounty_registry):
    return bounty_registry.functions.PAGE_SIZE().call()


# noinspection PyBroadException
@cache.memoize(30)
def substitute_metadata(
    uri, artifact_client, session, validate=AssertionMetadata.validate, redis=None
):
    """
    Download metadata from artifact service and validate it against the schema.

    :param uri: Potential artifact service uri string (or metadata string)
    :param artifact_client: Artifact Client for accessing artifacts stored on a service
    :param session: Requests session for ipfs request
    :param validate: Function that takes a loaded json blob and returns true if it matches the schema
    :param redis: Redis connection object
    :return: Metadata from artifact service, or original metadata
    """
    try:
        if artifact_client.check_uri(uri):
            content = json.loads(
                artifact_client.get_artifact(uri, session=session, redis=redis).decode('utf-8')
            )
        else:
            content = json.loads(uri)

        if validate(content):
            return content

    except json.JSONDecodeError:
        # Expected when people provide incorrect metadata. Not stack worthy
        logger.warning('Metadata retrieved from IPFS does not match schema')
    except Exception:
        logger.exception(f'Error getting metadata from {artifact_client.name}')

    return uri


@bounties.route('', methods=['GET'])
@chain
@cache.memoize(60)
def get_bounties():
    page_size = get_page_size()
    page = request.args.get('page', 0)
    count = request.args.get('count', page_size)

    page_size_multiplier = count / page_size
    if count % page_size != 0 and page_size_multiplier <= MAX_PAGES_PER_REQUEST:
        return failure(f'Count must be a multiple of page size {page_size}', 400)

    guids = []
    start_page = page * page_size_multiplier
    for i in range(page_size_multiplier):
        page_guids = get_bounty_guids_page(start_page + i)
        if not page_guids:
            break

        guids.extend(page_guids)

    return success(guids)


_post_bounties_schema = fastjsonschema.compile({
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
            'pattern': r'^\d+$'
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
})


@bounties.route('', methods=['POST'])
@chain
def post_bounties():
    config = app.config['POLYSWARMD']
    session = app.config['REQUESTS_SESSION']
    account = g.chain.w3.toChecksumAddress(g.eth_address)
    base_nonce = int(request.args.get('base_nonce', g.chain.w3.eth.getTransactionCount(account)))

    body = request.get_json()
    try:
        _post_bounties_schema(body)
    except fastjsonschema.JsonSchemaException as e:
        return failure('Invalid JSON: ' + e.message, 400)

    guid = uuid.uuid4()
    artifact_type = ArtifactType.from_string(body['artifact_type'])
    amount = int(body['amount'])
    artifact_uri = body['uri']
    duration_blocks = body['duration']
    metadata = body.get('metadata', '')

    try:
        arts = config.artifact_client.ls(artifact_uri, session)
    except HTTPError as e:
        return failure(e.response.content, e.response.status_code)
    except ArtifactException:
        logger.exception('Failed to ls given artifact uri')
        return failure(f'Failed to check artifact uri', 500)

    if amount < eth.bounty_amount_min(g.chain.bounty_registry.contract) * len(arts):
        return failure('Invalid bounty amount', 400)

    if metadata and not config.artifact_client.check_uri(metadata):
        return failure('Invalid bounty metadata URI (should be IPFS hash)', 400)

    num_artifacts = len(arts)
    bloom = calculate_bloom(arts)

    approve_amount = amount + eth.bounty_fee(g.chain.bounty_registry.contract)

    transactions = [
        build_transaction(
            g.chain.nectar_token.contract.functions.approve(
                g.chain.bounty_registry.contract.address, approve_amount
            ), base_nonce
        ),
        build_transaction(
            g.chain.bounty_registry.contract.functions.postBounty(
                guid.int, artifact_type.value, amount, artifact_uri, num_artifacts, duration_blocks,
                bloom, metadata
            ), base_nonce + 1
        ),
    ]

    return success({'transactions': transactions})


@bounties.route('/parameters', methods=['GET'])
@cache.memoize(1)
@chain
def get_bounty_parameters():
    bounty_fee = g.chain.bounty_registry.contract.functions.bountyFee().call()
    assertion_fee = g.chain.bounty_registry.contract.functions.assertionFee().call()
    bounty_amount_minimum = g.chain.bounty_registry.contract.functions.BOUNTY_AMOUNT_MINIMUM().call()
    assertion_bid_minimum = g.chain.bounty_registry.contract.functions.ASSERTION_BID_ARTIFACT_MINIMUM(
    ).call()
    assertion_bid_maximum = g.chain.bounty_registry.contract.functions.ASSERTION_BID_ARTIFACT_MAXIMUM(
    ).call()
    arbiter_lookback_range = g.chain.bounty_registry.contract.functions.ARBITER_LOOKBACK_RANGE(
    ).call()
    max_duration = g.chain.bounty_registry.contract.functions.MAX_DURATION().call()
    assertion_reveal_window = g.chain.bounty_registry.contract.functions.assertionRevealWindow(
    ).call()
    arbiter_vote_window = g.chain.bounty_registry.contract.functions.arbiterVoteWindow().call()

    return success({
        'bounty_fee': bounty_fee,
        'assertion_fee': assertion_fee,
        'bounty_amount_minimum': bounty_amount_minimum,
        'assertion_bid_maximum': assertion_bid_maximum,
        'assertion_bid_minimum': assertion_bid_minimum,
        'arbiter_lookback_range': arbiter_lookback_range,
        'max_duration': max_duration,
        'assertion_reveal_window': assertion_reveal_window,
        'arbiter_vote_window': arbiter_vote_window
    })


@bounties.route('/<uuid:guid>', methods=['GET'])
@chain
def get_bounties_guid(guid):
    config = app.config['POLYSWARMD']
    session = app.config['REQUESTS_SESSION']
    bounty = bounty_to_dict(
        g.chain.bounty_registry.contract.functions.bountiesByGuid(guid.int).call()
    )
    metadata = bounty.get('metadata', None)
    if metadata:
        metadata = substitute_metadata(
            metadata,
            config.artifact_client,
            session,
            validate=BountyMetadata.validate,
            redis=config.redis
        )
    else:
        metadata = None
    bounty['metadata'] = metadata
    if not config.artifact_client.check_uri(bounty['uri']):
        return failure(f'Invalid {config.artifact_client.name} URI', 400)
    if bounty['author'] == ZERO_ADDRESS:
        return failure('Bounty not found', 404)

    return success(bounty)


_post_bounties_guid_vote_schema = fastjsonschema.compile({
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
})


@bounties.route('/<uuid:guid>/vote', methods=['POST'])
@chain
def post_bounties_guid_vote(guid):
    account = g.chain.w3.toChecksumAddress(g.eth_address)
    base_nonce = int(request.args.get('base_nonce', g.chain.w3.eth.getTransactionCount(account)))

    body = request.get_json()
    try:
        _post_bounties_guid_vote_schema(body)
    except fastjsonschema.JsonSchemaException as e:
        return failure('Invalid JSON: ' + e.message, 400)

    votes = bool_list_to_int(body['votes'])
    valid_bloom = bool(body['valid_bloom'])

    transactions = [
        build_transaction(
            g.chain.bounty_registry.contract.functions.voteOnBounty(guid.int, votes, valid_bloom),
            base_nonce
        ),
    ]
    return success({'transactions': transactions})


@bounties.route('/<uuid:guid>/settle', methods=['POST'])
@chain
def post_bounties_guid_settle(guid):
    account = g.chain.w3.toChecksumAddress(g.eth_address)
    base_nonce = int(request.args.get('base_nonce', g.chain.w3.eth.getTransactionCount(account)))

    transactions = [
        build_transaction(
            g.chain.bounty_registry.contract.functions.settleBounty(guid.int), base_nonce
        )
    ]

    return success({'transactions': transactions})


# noinspection PyBroadException
@bounties.route('/metadata', methods=['POST'])
def post_assertion_metadata():
    config = app.config['POLYSWARMD']
    session = app.config['REQUESTS_SESSION']
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
        uri = config.artifact_client.add_artifact(body, session, redis=config.redis)
        response = success(uri)
    except HTTPError as e:
        response = failure(e.response.content, e.response.status_code)
    except ArtifactException as e:
        response = failure(e.message, 500)
    except Exception:
        logger.exception('Received error posting to IPFS got response')
        response = failure('Could not add metadata to ipfs', 500)

    return response


_post_bounties_guid_assertions_schema = fastjsonschema.compile({
    'type': 'object',
    'properties': {
        'bid': {
            'type': 'array',
            'minItems': 0,
            'maxItems': 256,
            'items': {
                'type': 'string',
                'minLength': 1,
                'maxLength': 100,
                'pattern': r'^\d+$',
            }
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
})


@bounties.route('/<uuid:guid>/assertions', methods=['POST'])
@chain
def post_bounties_guid_assertions(guid):
    account = g.chain.w3.toChecksumAddress(g.eth_address)
    base_nonce = int(request.args.get('base_nonce', g.chain.w3.eth.getTransactionCount(account)))

    body = request.get_json()
    try:
        _post_bounties_guid_assertions_schema(body)
    except fastjsonschema.JsonSchemaException as e:
        return failure('Invalid JSON: ' + e.message, 400)

    bid = [int(b) for b in body['bid']]
    mask = bool_list_to_int(body['mask'])
    verdict_count = len([m for m in body['mask'] if m])

    commitment = body.get('commitment')
    verdicts = body.get('verdicts')

    if commitment is None and verdicts is None:
        return failure('Require verdicts and bid_portions or a commitment', 400)

    if not bid or len(bid) != verdict_count:
        return failure('bid_portions must be equal in length to the number of true mask values', 400)

    max_bid = eth.assertion_bid_max(g.chain.bounty_registry.contract)
    min_bid = eth.assertion_bid_min(g.chain.bounty_registry.contract)
    if any((b for b in bid if max_bid < b < min_bid)):
        return failure('Invalid assertion bid', 400)

    approve_amount = sum(bid) + eth.assertion_fee(g.chain.bounty_registry.contract)

    nonce = None
    if commitment is None:
        nonce, commitment = calculate_commitment(account, bool_list_to_int(verdicts))
    else:
        commitment = int(commitment)

    ret = {
        'transactions': [
            build_transaction(
                g.chain.nectar_token.contract.functions.approve(
                    g.chain.bounty_registry.contract.address, approve_amount
                ), base_nonce
            ),
            build_transaction(
                g.chain.bounty_registry.contract.functions.postAssertion(
                    guid.int, bid, mask, commitment
                ), base_nonce + 1
            ),
        ]
    }

    if nonce is not None:
        # Pass generated nonce onto user in response, used for reveal
        ret['nonce'] = nonce

    return success(ret)


_post_bounties_guid_assertions_id_reveal_schema = fastjsonschema.compile({
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
})


@bounties.route('/<uuid:guid>/assertions/<int:id_>/reveal', methods=['POST'])
@chain
def post_bounties_guid_assertions_id_reveal(guid, id_):
    account = g.chain.w3.toChecksumAddress(g.eth_address)
    base_nonce = int(request.args.get('base_nonce', g.chain.w3.eth.getTransactionCount(account)))

    body = request.get_json()
    try:
        _post_bounties_guid_assertions_id_reveal_schema(body)
    except fastjsonschema.JsonSchemaException as e:
        return failure('Invalid JSON: ' + e.message, 400)

    nonce = int(body['nonce'])
    verdicts = bool_list_to_int(body['verdicts'])
    metadata = body['metadata']

    transactions = [
        build_transaction(
            g.chain.bounty_registry.contract.functions.revealAssertion(
                guid.int, id_, nonce, verdicts, metadata
            ), base_nonce
        ),
    ]
    return success({'transactions': transactions})


@bounties.route('/<uuid:guid>/assertions', methods=['GET'])
@chain
def get_bounties_guid_assertions(guid):
    bounty = bounty_to_dict(
        g.chain.bounty_registry.contract.functions.bountiesByGuid(guid.int).call()
    )
    if bounty['author'] == ZERO_ADDRESS:
        return failure('Bounty not found', 404)

    num_assertions = g.chain.bounty_registry.contract.functions.getNumberOfAssertions(guid.int
                                                                                      ).call()
    assertions = []
    for i in range(num_assertions):
        try:
            assertion = get_assertion(guid, i, bounty['num_artifacts'])
            # Nonce is 0 when a reveal did not occur
            if assertion['nonce'] == "0":
                assertion['verdicts'] = [None] * bounty['num_artifacts']
            assertions.append(assertion)
        except Exception:
            logger.exception('Could not retrieve assertion')
            continue

    return success(assertions)


@bounties.route('/<uuid:guid>/assertions/<int:id_>', methods=['GET'])
@chain
def get_bounties_guid_assertions_id(guid, id_):
    bounty = bounty_to_dict(
        g.chain.bounty_registry.contract.functions.bountiesByGuid(guid.int).call()
    )
    if bounty['author'] == ZERO_ADDRESS:
        return failure('Bounty not found', 404)

    try:
        assertion = get_assertion(guid, id_, bounty['num_artifacts'])
        return success(assertion)
    except:  # noqa: E772
        return failure('Assertion not found', 404)


@bounties.route('/<uuid:guid>/votes', methods=['GET'])
@chain
def get_bounties_guid_votes(guid):
    bounty = bounty_to_dict(
        g.chain.bounty_registry.contract.functions.bountiesByGuid(guid.int).call()
    )
    if bounty['author'] == ZERO_ADDRESS:
        return failure('Bounty not found', 404)

    num_votes = g.chain.bounty_registry.contract.functions.getNumberOfVotes(guid.int).call()

    votes = []
    for i in range(num_votes):
        try:
            vote = vote_to_dict(
                g.chain.bounty_registry.contract.functions.votesByGuid(guid.int, i).call(),
                bounty['num_artifacts']
            )
            votes.append(vote)
        except Exception:
            logger.exception('Could not retrieve vote')
            continue

    return success(votes)


@bounties.route('/<uuid:guid>/votes/<int:id_>', methods=['GET'])
@chain
def get_bounties_guid_votes_id(guid, id_):
    bounty = bounty_to_dict(
        g.chain.bounty_registry.contract.functions.bountiesByGuid(guid.int).call()
    )
    if bounty['author'] == ZERO_ADDRESS:
        return failure('Bounty not found', 404)

    try:
        vote = vote_to_dict(
            g.chain.bounty_registry.contract.functions.votesByGuid(guid.int, id_).call(),
            bounty['num_artifacts']
        )
        return success(vote)
    except:  # noqa: E772
        return failure('Vote not found', 404)


@bounties.route('/<uuid:guid>/bloom', methods=['GET'])
@cache.memoize(30)
@chain
def get_bounties_guid_bloom(guid):
    bounty = bounty_to_dict(
        g.chain.bounty_registry.contract.functions.bountiesByGuid(guid.int).call()
    )
    if bounty['author'] == ZERO_ADDRESS:
        return failure('Bounty not found', 404)

    try:
        bloom_parts = []
        for i in range(0, 8):
            bloom_parts.append(
                g.chain.bounty_registry.contract.functions.bloomByGuid(guid.int, i).call()
            )
        bloom = bloom_to_dict(bloom_parts)
        return success(bloom)
    except:  # noqa: E772
        logger.exception('Bloom not found')
        return failure('Bloom not found', 404)
