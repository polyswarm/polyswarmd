import uuid
import jsonschema

from flask import Blueprint, request
from jsonschema.exceptions import ValidationError
from polyswarmd.eth import web3, nectar_token, bounty_registry
from polyswarmd.response import success, failure
from polyswarmd.websockets import transaction_queue
from polyswarmd.utils import new_bounty_event_to_dict, new_assertion_event_to_dict, new_verdict_event_to_dict

bounties = Blueprint('bounties', __name__)


@bounties.route('', methods=['POST'])
def post_bounties():
    account = request.args.get('account')
    if not account or not web3.isAddress(account):
        return failure('Source account required', 401)

    schema = {
        'type': 'object',
        'properties': {
            'amount': {
                'type': 'string',
                'minLength': 1,
                'maxLength': 64,
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

    if amount < eth.bounty_amount_min:
        return failure('Invalid bounty amount', 400)

    if not is_valid_ipfshash(artifactURI):
        return failure('Invalid artifact URI (should be IPFS hash)', 400)

    approveAmount = amount + eth.bounty_fee()

    tx = transaction_queue.send_transaction(
        nectar_token.functions.approve(bounty_registry.address, approveAmount),
        account).get()
    if not check_transaction(tx):
        return failure(
            'Approve transaction failed, verify parameters and try again', 400)
    tx = transaction_queue(
        bounty_registry.functions.postBounty(guid.int, amount, artifactURI,
                                             durationBlocks), account).get()
    if not check_transaction(tx):
        return failure(
            'Post bounty transaction failed, verify parameters and try again',
            400)

    receipt = web3.eth.getTransactionReceipt(tx)
    processed = bounty_registry.events.NewBounty().processReceipt(receipt)
    if len(processed) == 0:
        return failure(
            'Invalid transaction receipt, no events emitted. Check contract addresses',
            400)
    new_bounty_event = processed[0]['args']
    return success(new_bounty_event_to_dict(new_bounty_event))


# TODO: Caching layer for this
@bounties.route('', methods=['GET'])
def get_bounties():
    num_bounties = bounty_registry.functions.getNumberOfBounties().call()
    bounties = []
    for i in range(num_bounties):
        guid = bounty_registry.functions.bountyGuids(i).call()
        bounties.append(
            bounty_to_dict(
                bounty_registry.functions.bountiesByGuid(guid).call()))

    return success(bounties)


# TODO: Caching layer for this
@bounties.route('/active', methods=['GET'])
def get_bounties_active():
    current_block = web3.eth.blockNumber
    num_bounties = bounty_registry.functions.getNumberOfBounties().call()
    bounties = []
    for i in range(num_bounties):
        guid = bounty_registry.functions.bountyGuids(i).call()
        bounty = bounty_to_dict(
            bounty_registry.functions.bountiesByGuid(guid).call())

        if bounty['expiration'] > current_block:
            bounties.append(bounty)

    return success(bounties)


# TODO: Caching layer for this
@bounties.route('/pending', methods=['GET'])
def get_bounties_pending():
    current_block = web3.eth.blockNumber
    num_bounties = bounty_registry.functions.getNumberOfBounties().call()
    bounties = []
    for i in range(num_bounties):
        guid = bounty_registry.functions.bountyGuids(i).call()
        bounty = bounty_to_dict(
            bounty_registry.functions.bountiesByGuid(guid).call())

        if bounty['expiration'] <= current_block and not bounty['resolved']:
            bounties.append(bounty)

    return success(bounties)


@bounties.route('/<uuid:guid>', methods=['GET'])
def get_bounties_guid(guid):
    bounty = bounty_to_dict(
        bounty_registry.functions.bountiesByGuid(guid.int).call())
    if bounty['author'] == ZERO_ADDRESS:
        return failure('Bounty not found', 404)
    else:
        return success(bounty)


@bounties.route('/<uuid:guid>/settle', methods=['POST'])
def post_bounties_guid_settle(guid):
    account = request.args.get('account')
    if not account or not web3.isAddress(account):
        return failure('Source account required', 401)

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
        },
        'required': ['verdicts'],
    }

    body = request.get_json()
    try:
        jsonschema.validate(body, schema)
    except ValidationError as e:
        return failure('Invalid JSON: ' + e.message, 400)

    verdicts = bool_list_to_int(body['verdicts'])

    tx = transaction_queue.send_transaction(
        bounty_registry.functions.settleBounty(guid.int, verdicts),
        account).get()
    if not check_transaction(tx):
        return failure(
            'Settle bounty transaction failed, verify parameters and try again',
            400)

    receipt = web3.eth.getTransactionReceipt(tx)
    processed = bounty_registry.events.NewVerdict().processReceipt(receipt)
    if len(processed) == 0:
        return failure(
            'Invalid transaction receipt, no events emitted. Check contract addresses',
            400)
    new_verdict_event = processed[0]['args']
    return success(new_verdict_event_to_dict(new_verdict_event))


@bounties.route('/<uuid:guid>/assertions', methods=['POST'])
def post_bounties_guid_assertions(guid):
    account = request.args.get('account')
    if not account or not web3.isAddress(account):
        return failure('Source account required', 401)

    schema = {
        'type': 'object',
        'properties': {
            'bid': {
                'type': 'string',
                'minLength': 1,
                'maxLength': 64,
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
            'metadata': {
                'type': 'string',
                'maxLength': 1024,
            },
        },
        'required': ['bid', 'mask', 'verdicts', 'metadata'],
    }

    body = request.get_json()
    try:
        jsonschema.validate(body, schema)
    except ValidationError as e:
        return failure('Invalid JSON: ' + e.message, 400)

    bid = int(body['bid'])
    mask = bool_list_to_int(body['mask'])
    verdicts = bool_list_to_int(body['verdicts'])
    metadata = body['metadata']

    if bid < eth.assertion_bid_min():
        return failure('Invalid assertion bid', 400)

    approveAmount = bid + eth.assertion_fee()

    tx = transaction_queue.send_transaction(
        nectar_token.functions.approve(bounty_registry.address, approveAmount),
        account).get()
    if not check_transaction(tx):
        return failure(
            'Approve transaction failed, verify parameters and try again', 400)

    tx = transaction_queue.send_transaction(
        bounty_registry.functions.postAssertion(guid.int, bid, mask, verdicts,
                                                metadata), account).get()
    if not check_transaction(tx):
        return failure(
            'Post assertion transaction failed, verify parameters and try again',
            400)

    receipt = web3.eth.getTransactionReceipt(tx)
    processed = bounty_registry.events.NewAssertion().processReceipt(receipt)
    if len(processed) == 0:
        return failure(
            'Invalid transaction receipt, no events emitted. Check contract addresses',
            400)
    new_assertion_event = processed[0]['args']
    return success(new_assertion_event_to_dict(new_assertion_event))


@bounties.route('/<uuid:guid>/assertions', methods=['GET'])
def get_bounties_guid_assertions(guid):
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
    try:
        return success(
            assertion_to_dict(
                bounty_registry.functions.assertionsByGuid(guid.int,
                                                           id_).call()))
    except:
        return failure('Assertion not found', 404)
