import uuid
import jsonschema

from flask import Blueprint, request
from jsonschema.exceptions import ValidationError
from polyswarmd.eth import web3, nectar_token, bounty_registry
from polyswarmd.response import success, failure

bounties = Blueprint('bounties', __name__)

def bounty_to_dict(bounty):
    return {
        'guid': str(uuid.UUID(int=bounty[0])),
        'author': bounty[1],
        'amount': str(bounty[2]),
        'uri': bounty[3],
        'expiration': bounty[4],
        'resolved': bounty[5],
        'verdicts': int_to_bool_list(bounty[6]),
    }

def new_bounty_event_to_dict(new_bounty_event):
    return {
        'guid': str(uuid.UUID(int=new_bounty_event.guid)),
        'author': new_bounty_event.author,
        'amount': str(new_bounty_event.amount),
        'uri': new_bounty_event.artifactURI,
        'expiration': str(new_bounty_event.expirationBlock),
    }

def assertion_to_dict(assertion):
    return {
        'author': assertion[0],
        'bid': str(assertion[1]),
        'mask': int_to_bool_list(assertion[2]),
        'verdicts': int_to_bool_list(assertion[3]),
        'metadata': assertion[4],
    }

def new_assertion_event_to_dict(new_assertion_event):
    return {
        'bounty_guid': str(uuid.UUID(int=new_assertion_event.bountyGuid)),
        'author': new_assertion_event.author,
        'index': new_assertion_event.index,
        'bid': str(new_assertion_event.bid),
        'mask': int_to_bool_list(new_assertion_event.mask),
        'verdicts': int_to_bool_list(new_assertion_event.verdicts),
        'metadata': new_assertion_event.metadata,
    }

def new_verdict_event_to_dict(new_verdict_event):
    return {
        'bounty_guid': str(uuid.UUID(int=new_verdict_event.bountyGuid)),
        'verdicts': int_to_bool_list(new_verdict_event.verdicts),
    }

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

#    tx = nectar_token.functions.approve(
#        bounty_registry.address, approveAmount
#    ).transact({'from': active_account, 'gasLimit': 200000})
#    if not check_transaction(tx):
#        return failure('Approve transaction failed, verify parameters and try again', 400)
#
#    tx = bounty_registry.functions.postBounty(
#        guid.int, amount, artifactURI, durationBlocks
#    ).transact({'from': active_account, 'gasLimit': 200000})
#    if not check_transaction(tx):
#        return failure('Post bounty transaction failed, verify parameters and try again', 400)

    receipt = web3.eth.getTransactionReceipt(tx)
    processed = bounty_registry.events.NewBounty().processReceipt(receipt)
    if len(processed) == 0:
        return failure('Invalid transaction receipt, no events emitted. Check contract addresses', 400)
    new_bounty_event = processed[0]['args']
    return success(new_bounty_event_to_dict(new_bounty_event))

# TODO: Caching layer for this
@bounties.route('', methods=['GET'])
def get_bounties():
    num_bounties = bounty_registry.functions.getNumberOfBounties().call()
    bounties = []
    for i in range(num_bounties):
        guid = bounty_registry.functions.bountyGuids(i).call()
        bounties.append(bounty_to_dict(
            bounty_registry.functions.bountiesByGuid(guid).call()
        ))

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
            bounty_registry.functions.bountiesByGuid(guid).call()
        )

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
        bounty = bounty_to_dict(bounty_registry.functions.bountiesByGuid(guid).call())

        if bounty['expiration'] <= current_block and not bounty['resolved']:
            bounties.append(bounty)

    return success(bounties)

@bounties.route('/<uuid:guid>', methods=['GET'])
def get_bounties_guid(guid):
    bounty = bounty_to_dict(bounty_registry.functions.bountiesByGuid(guid.int).call())
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

#    tx = bounty_registry.functions.settleBounty(
#        guid.int, verdicts
#    ).transact({'from': active_account, 'gasLimit': 1000000})
#    if not check_transaction(tx):
#        return failure('Settle bounty transaction failed, verify parameters and try again', 400)

    receipt = web3.eth.getTransactionReceipt(tx)
    processed = bounty_registry.events.NewVerdict().processReceipt(receipt)
    if len(processed) == 0:
        return failure('Invalid transaction receipt, no events emitted. Check contract addresses', 400)
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

#    tx = nectar_token.functions.approve(
#        bounty_registry.address, approveAmount
#    ).transact({'from': active_account, 'gasLimit': 200000})
#    if not check_transaction(tx):
#        return failure('Approve transaction failed, verify parameters and try again', 400)
#
#    tx = bounty_registry.functions.postAssertion(
#        guid.int, bid, mask, verdicts, metadata
#    ).transact({'from': active_account, 'gasLimit': 200000})
#    if not check_transaction(tx):
#        return failure('Post assertion transaction failed, verify parameters and try again', 400)

    receipt = web3.eth.getTransactionReceipt(tx)
    processed = bounty_registry.events.NewAssertion().processReceipt(receipt)
    if len(processed) == 0:
        return failure('Invalid transaction receipt, no events emitted. Check contract addresses', 400)
    new_assertion_event = processed[0]['args']
    return success(new_assertion_event_to_dict(new_assertion_event))

@bounties.route('/<uuid:guid>/assertions', methods=['GET'])
def get_bounties_guid_assertions(guid):
    num_assertions = bounty_registry.functions.getNumberOfAssertions(guid.int).call()
    assertions = []
    for i in range(num_assertions):
        assertion = assertion_to_dict(bounty_registry.functions.assertionsByGuid(guid.int, i).call())
        assertions.append(assertion)

    return success(assertions)

@bounties.route('/<uuid:guid>/assertions/<int:id_>', methods=['GET'])
def get_bounties_guid_assertions_id(guid, id_):
    try:
        return success(assertion_to_dict(bounty_registry.functions.assertionsByGuid(guid.int, id_).call()))
    except:
        return failure('Assertion not found', 404)
