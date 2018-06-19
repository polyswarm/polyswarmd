import uuid

import json
import jsonschema
from jsonschema.exceptions import ValidationError

from flask import Blueprint, request

from websocket import create_connection

from polyswarmd.eth import web3 as web3_chains, check_transaction, nectar_token, offer_registry, bind_contract, offer_msig_artifact, offer_lib
from polyswarmd.response import success, failure
from polyswarmd.websockets import transaction_queue as transaction_queue_chain
from polyswarmd.utils import channel_to_dict
chain = 'home' # only on home chain
offers = Blueprint('offers', __name__)


@offers.route('', methods=['POST'])
def post_create_offer_channel():
    web3 = web3_chains[chain]
    transaction_queue = transaction_queue_chain[chain]
    account = request.args.get('account')
    if not account or not web3.isAddress(account):
        return failure('Source account required', 401)
    account = web3.toChecksumAddress(account)

    body = request.get_json()

    schema = {
        'type': 'object',
        'properties': {
            'ambassador': {
                'type': 'string',
                'minLength': 42,
            },
            'expert': {
                'type': 'string',
                'minLength': 42,
            },
            'settlementPeriodLength': {
                'type': 'integer',
                'minimum': 0,
            },
            'websocketUri': {
                'type': 'string',
                'minLength': 1,
                'maxLength': 32
            }
        },
        'required': ['ambassador', 'expert', 'settlementPeriodLength', 'websocketUri'],
    }

    try:
        jsonschema.validate(body, schema)
    except ValidationError as e:
        return failure('Invalid JSON: ' + e.message)

    guid = uuid.uuid4()
    ambassador = web3.toChecksumAddress(body['ambassador'])
    expert = web3.toChecksumAddress(body['expert'])
    settlement_period_length = body['settlementPeriodLength']
    websocket_uri = body['websocketUri']

    tx = transaction_queue.send_transaction(
        offer_registry.functions.initializeOfferChannel(guid.int, ambassador, expert, settlement_period_length),
        account).get()

    if not check_transaction(web3, tx):
        return failure(
            'The offer contract deploy transaction failed, verify parameters and try again', 400)

    receipt = web3.eth.getTransactionReceipt(tx)

    processed = offer_registry.events.InitializedChannel().processReceipt(receipt)

    if not processed:
        return failure(
            'Invalid transaction receipt, no events emitted. Check contract addresses',
            400)

    success_dict = dict(processed[0]['args'])

    msig_address = success_dict['msig']

    offer_msig = bind_contract(web3, msig_address, offer_msig_artifact)

    tx = transaction_queue.send_transaction(
        offer_msig.functions.setCommunicationUri(web3.toHex(text=websocket_uri)),
        account).get()

    if not check_transaction(web3, tx):
        return failure(
            'Failed to set to set socket url verify parameters and use the setWebsocket/ endpoint to try again', 400)

    receipt = web3.eth.getTransactionReceipt(tx)

    processed = offer_msig.events.CommunicationsSet().processReceipt(receipt)

    success_dict['websocketUri'] = offer_msig.functions.websocketUri().call()
    # TODO find a better way than replace
    success_dict['websocketUri'] = web3.toText(success_dict['websocketUri']).replace('\u0000', '')

    success_dict['guid'] = uuid.UUID(int=success_dict['guid'])

    return success(success_dict)


@offers.route('/<uuid:guid>/open', methods=['POST'])
def post_open(guid):
    web3 = web3_chains[chain]
    transaction_queue = transaction_queue_chain[chain]
    account = request.args.get('account')
    if not account or not web3.isAddress(account):
        return failure('Source account required', 401)
    account = web3.toChecksumAddress(account)

    offer_channel = channel_to_dict(offer_registry.functions.guidToChannel(guid.int).call())
    msig_address = offer_channel['msig_address']

    body = request.get_json()

    schema = {
        'type': 'object',
        'properties': {
            'state': {
                'type': 'string',
                'minLength': 32,
            },
            'r': {
                'type': 'string',
                'minLength': 64,
            },
            'v': {
                'type': 'integer',
                'minimum': 0,
            },
            's': {
                'type': 'string',
                'minLength': 64
            }
        },
        'required': ['state', 'r', 'v', 's'],
    }

    try:
        jsonschema.validate(body, schema)
    except ValidationError as e:
        return failure('Invalid JSON: ' + e.message)

    state = body['state']
    v = body['v']
    r = body['r']
    s = body['s']

    offer_msig = bind_contract(web3, msig_address, offer_msig_artifact)
    approve_amount = offer_lib.functions.getBalanceA(state).call()
    tx = transaction_queue.send_transaction(
        nectar_token['home'].functions.approve(msig_address, approve_amount),
        account).get()
    if not check_transaction(web3, tx):
        return failure(
            'Approve transaction failed, verify parameters and try again', 400)

    tx = transaction_queue.send_transaction(
        offer_msig.functions.openAgreement(state, v, r, s),
        account).get()

    if not check_transaction(web3, tx):
        return failure(
            'Failed to open agreement, verify parameters and try again', 400)

    receipt = web3.eth.getTransactionReceipt(tx)

    processed = offer_msig.events.OpenedAgreement().processReceipt(receipt)

    if not processed:
        return failure(
            'Invalid transaction receipt, no events emitted. Check contract addresses',
            400)

    data = dict(processed[0]['args'])

    return success(data)

@offers.route('/<uuid:guid>/cancel', methods=['POST'])
def post_cancel(guid):
    web3 = web3_chains[chain]
    transaction_queue = transaction_queue_chain[chain]
    account = request.args.get('account')
    if not account or not web3.isAddress(account):
        return failure('Source account required', 401)
    account = web3.toChecksumAddress(account)

    offer_channel = channel_to_dict(offer_registry.functions.guidToChannel(guid.int).call())
    msig_address = offer_channel['msig_address']

    offer_msig = bind_contract(web3, msig_address, offer_msig_artifact)

    tx = transaction_queue.send_transaction(
        offer_msig.functions.cancel(),
        account).get()

    if not check_transaction(tx):
        return failure(
            'Failed to cancel agreement, make sure this channel has not been joined and try again', 400)

    receipt = web3.eth.getTransactionReceipt(tx)

    processed = offer_msig.events.CanceledAgreement().processReceipt(receipt)

    if not processed:
        return failure(
            'Invalid transaction receipt, no events emitted. Check contract addresses',
            400)

    data = dict(processed[0]['args'])

    return success(data)

@offers.route('/<uuid:guid>/join', methods=['POST'])
def post_join(guid):
    web3 = web3_chains[chain]
    transaction_queue = transaction_queue_chain[chain]
    account = request.args.get('account')
    if not account or not web3.isAddress(account):
        return failure('Source account required', 401)
    account = web3.toChecksumAddress(account)

    offer_channel = channel_to_dict(offer_registry.functions.guidToChannel(guid.int).call())
    msig_address = offer_channel['msig_address']

    body = request.get_json()

    schema = {
        'type': 'object',
        'properties': {
            'state': {
                'type': 'string',
                'minLength': 32,
            },
            'r': {
                'type': 'string',
                'minLength': 64,
            },
            'v': {
                'type': 'integer',
                'minimum': 0,
            },
            's': {
                'type': 'string',
                'minLength': 64
            }
        },
        'required': ['state', 'r', 'v', 's'],
    }

    try:
        jsonschema.validate(body, schema)
    except ValidationError as e:
        return failure('Invalid JSON: ' + e.message)

    state = body['state']
    v = body['v']
    r = body['r']
    s = body['s']

    offer_msig = bind_contract(web3, msig_address, offer_msig_artifact)

    tx = transaction_queue.send_transaction(
        offer_msig.functions.joinAgreement(state, v, r, s),
        account).get()

    if not check_transaction(web3, tx):
        return failure(
            'Failed to open agreement, verify parameters and try again', 400)

    receipt = web3.eth.getTransactionReceipt(tx)

    processed = offer_msig.events.JoinedAgreement().processReceipt(receipt)

    if not processed:
        return failure(
            'Invalid transaction receipt, no events emitted. Check contract addresses',
            400)

    data = dict(processed[0]['args'])

    return success(data)

@offers.route('/<uuid:guid>/close', methods=['POST'])
def post_close(guid):
    web3 = web3_chains[chain]
    transaction_queue = transaction_queue_chain[chain]
    account = request.args.get('account')
    if not account or not web3.isAddress(account):
        return failure('Source account required', 401)
    account = web3.toChecksumAddress(account)

    offer_channel = channel_to_dict(offer_registry.functions.guidToChannel(guid.int).call())
    msig_address = offer_channel['msig_address']

    body = request.get_json()

    schema = {
        'type': 'object',
        'properties': {
            'state': {
                'type': 'string',
                'minLength': 32,
            },
            'r': {
                'type': 'array',
                'minLength': 2,
                'maxLength': 2,
            },
            'v': {
                'type': 'array',
                'minLength': 2,
                'maxLength': 2,
            },
            's': {
                'type': 'array',
                'minLength': 2,
                'maxLength': 2,
            }
        },
        'required': ['state', 'r', 'v', 's'],
    }

    try:
        jsonschema.validate(body, schema)
    except ValidationError as e:
        return failure('Invalid JSON: ' + e.message)

    state = body['state']
    v = body['v']
    r = body['r']
    s = body['s']


    offer_msig = bind_contract(web3, msig_address, offer_msig_artifact)

    tx = transaction_queue.send_transaction(
        offer_msig.functions.closeAgreement(state, v, r, s),
        account).get()

    if not check_transaction(web3, tx):
        return failure(
            'Failed to close agreement, verify parameters and try again', 400)

    receipt = web3.eth.getTransactionReceipt(tx)

    processed = offer_msig.events.ClosedAgreement().processReceipt(receipt)

    if not processed:
        return failure(
            'Invalid transaction receipt, no events emitted. Check contract addresses',
            400)

    data = dict(processed[0]['args'])

    return success(data)

# for closing a challenged state with a timeout
@offers.route('/<uuid:guid>/closeChallenged', methods=['POST'])
def post_close_challenged(guid):
    web3 = web3_chains[chain]
    transaction_queue = transaction_queue_chain[chain]
    account = request.args.get('account')
    if not account or not web3.isAddress(account):
        return failure('Source account required', 401)
    account = web3.toChecksumAddress(account)

    offer_channel = channel_to_dict(offer_registry.functions.guidToChannel(guid.int).call())
    msig_address = offer_channel['msig_address']

    body = request.get_json()
    
    schema = {
        'type': 'object',
        'properties': {
            'state': {
                'type': 'string',
                'minLength': 32,
            },
            'r': {
                'type': 'array',
                'minLength': 2,
            },
            'v': {
                'type': 'array',
                'minimum': 2,
            },
            's': {
                'type': 'array',
                'minLength': 2
            }
        },
        'required': ['state', 'r', 'v', 's'],
    }

    try:
        jsonschema.validate(body, schema)
    except ValidationError as e:
        return failure('Invalid JSON: ' + e.message)

    state = body['state']
    v = body['v']
    r = body['r']
    s = body['s']

    offer_msig = bind_contract(web3, msig_address, offer_msig_artifact)

    tx = transaction_queue.send_transaction(
        offer_msig.functions.closeAgreementWithTimeout(state, v, r, s),
        account).get()

    if not check_transaction(tx):
        return failure(
            'Failed to close agreement, verify parameters and try again', 400)

    return success()

@offers.route('/<uuid:guid>/settle', methods=['POST'])
def post_settle(guid):
    web3 = web3_chains[chain]
    transaction_queue = transaction_queue_chain[chain]
    account = request.args.get('account')
    if not account or not web3.isAddress(account):
        return failure('Source account required', 401)
    account = web3.toChecksumAddress(account)
    offer_channel = channel_to_dict(offer_registry.functions.guidToChannel(guid.int).call())
    msig_address = offer_channel['msig_address']

    body = request.get_json()

    schema = {
        'type': 'object',
        'properties': {
            'state': {
                'type': 'string',
                'minLength': 32,
            },
            'r': {
                'type': 'array',
                'minLength': 2,
                'maxLength': 2,
            },
            'v': {
                'type': 'array',
                'minLength': 2,
                'maxLength': 2,
            },
            's': {
                'type': 'array',
                'minLength': 2,
                'maxLength': 2,
            }
        },
        'required': ['state', 'r', 'v', 's'],
    }

    try:
        jsonschema.validate(body, schema)
    except ValidationError as e:
        return failure('Invalid JSON: ' + e.message)

    state = body['state']
    v = body['v']
    r = body['r']
    s = body['s']

    offer_msig = bind_contract(web3, msig_address, offer_msig_artifact)

    tx = transaction_queue.send_transaction(
        offer_msig.functions.startSettle(state, v, r, s),
        account).get()

    if not check_transaction(web3, tx):
        return failure(
            'Failed to open agreement, verify parameters and try again', 400)

    receipt = web3.eth.getTransactionReceipt(tx)

    processed = offer_msig.events.StartedSettle().processReceipt(receipt)

    if not processed:
        return failure(
            'Invalid transaction receipt, no events emitted. Check contract addresses',
            400)

    data = dict(processed[0]['args'])

    return success(data)

@offers.route('/<uuid:guid>/challenge', methods=['POST'])
def post_challange(guid):
    web3 = web3_chains[chain]
    transaction_queue = transaction_queue_chain[chain]
    account = request.args.get('account')
    if not account or not web3.isAddress(account):
        return failure('Source account required', 401)
    account = web3.toChecksumAddress(account)

    offer_channel = channel_to_dict(offer_registry.functions.guidToChannel(guid.int).call())
    msig_address = offer_channel['msig_address']

    body = request.get_json()

    schema = {
        'type': 'object',
        'properties': {
            'state': {
                'type': 'string',
                'minLength': 32,
            },
            'r': {
                'type': 'array',
                'minLength': 2,
                'maxLength': 2,
            },
            'v': {
                'type': 'array',
                'minLength': 2,
                'maxLength': 2,
            },
            's': {
                'type': 'array',
                'minLength': 2,
                'maxLength': 2,
            }
        },
        'required': ['state', 'r', 'v', 's'],
    }


    try:
        jsonschema.validate(body, schema)
    except ValidationError as e:
        return failure('Invalid JSON: ' + e.message)

    state = body['state']
    v = body['v']
    r = body['r']
    s = body['s']


    offer_msig = bind_contract(web3, msig_address, offer_msig_artifact)

    tx = transaction_queue.send_transaction(
        offer_msig.functions.challengeSettle(state, v, r, s),
        account).get()

    if not check_transaction(web3, tx):
        return failure(
            'Failed to open agreement, verify parameters and try again', 400)

    receipt = web3.eth.getTransactionReceipt(tx)

    processed = offer_msig.events.SettleStateChallenged().processReceipt(receipt)

    if not processed:
        return failure(
            'Invalid transaction receipt, no events emitted. Check contract addresses',
            400)

    data = dict(processed[0]['args'])

    return success(data)

@offers.route('/<uuid:guid>/sendmsg', methods=['POST'])
def post_message_sender(guid):
    web3 = web3_chains[chain]
    account = request.args.get('account')
    if not account or not web3.isAddress(account):
        return failure('Source account required', 401)
    account = web3.toChecksumAddress(account)


    body = request.get_json()

    # if the post data does not have toSocketUri this endpoint with use the socket_uri from the contract (the ambassador's)
    schema = {
        'type': 'object',
        'properties': {
            'to_socket': {
                'type': 'string',
                'minLength': 0,
            },
            'from_socket': {
                'type': 'string',
                'minLength': 0,
            },
            'state': {
                'type': 'string',
                'minLength': 32,
            },
            'r': {
                'type': 'string',
                'minLength': 64,
            },
            'v': {
                'type': 'integer',
                'minimum': 0,
            },
            's': {
                'type': 'string',
                'minLength': 64
            }
        },
        'required': ['state', 'from_socket'],
    }

    try:
        jsonschema.validate(body, schema)
    except ValidationError as e:
        return failure('Invalid JSON: ' + e.message)


    offer_channel = channel_to_dict(offer_registry.functions.guidToChannel(guid.int).call())
    msig_address = offer_channel['msig_address']
    offer_msig = bind_contract(web3, msig_address, offer_msig_artifact)
    socket_uri = offer_msig.functions.websocketUri().call()
    # TODO find a better way than replace
    socket_uri = web3.toText(socket_uri).replace('\u0000', '')

    try:
        if 'to_socket' in body:
            ws = create_connection(body['to_socket'])
        else:
            ws = create_connection(socket_uri)
    except:
        return failure(
            'Could not connect to socket. Check the addresses or wait for party to be online',
            400)

    body['sender'] = account

    ws.send(json.dumps(body))

    ws.close()

    return success({'sent': True})

@offers.route('/<uuid:guid>', methods=['GET'])
def get_channel_address(guid):
    offer_channel = offer_registry.functions.guidToChannel(guid.int).call()

    return success({'offer_channel': channel_to_dict(offer_channel)})

@offers.route('/<uuid:guid>/settlementPeriod', methods=['GET'])
def get_settlement_period(guid):
    web3 = web3_chains[chain]
    offer_channel = offer_registry.functions.guidToChannel(guid.int).call()
    channel_data = channel_to_dict(offer_channel)
    offer_msig = bind_contract(web3, channel_data['msig_address'], offer_msig_artifact)

    settlement_period_end = offer_msig.functions.settlementPeriodEnd().call()

    return success({'settlementPeriodEnd': settlement_period_end})

@offers.route('/<uuid:guid>/websocket', methods=['GET'])
def get_websocket(guid):
    web3 = web3_chains[chain]
    offer_channel = offer_registry.functions.guidToChannel(guid.int).call()
    channel_data = channel_to_dict(offer_channel)
    msig_address = channel_data['msig_address']
    offer_msig = bind_contract(web3, msig_address, offer_msig_artifact)
    socket_uri = offer_msig.functions.websocketUri().call()
    # TODO find a better way than replace
    socket_uri = web3.toText(socket_uri).replace('\u0000', '')

    return success({'websocket': socket_uri})

@offers.route('pending', methods=['GET'])
def get_pending():
    web3 = web3_chains[chain]
    offers_pending = []
    num_of_offers = offer_registry.functions.getNumberOfOffers().call()

    for i in range(0, num_of_offers):
        guid = offer_registry.functions.channelsGuids(i).call()
        offer_channel = offer_registry.functions.guidToChannel(guid).call()
        channel_data = channel_to_dict(offer_channel)
        msig_address = channel_data['msig_address']
        offer_msig = bind_contract(web3, msig_address, offer_msig_artifact)
        pending_channel = offer_msig.functions.isPending().call()
        if pending_channel:
            offers_pending.append({'guid': guid, 'address': msig_address})

    return success(offers_pending)

@offers.route('opened', methods=['GET'])
def get_opened():
    offers_opened = []
    web3 = web3_chains[chain]
    num_of_offers = offer_registry.functions.getNumberOfOffers().call()

    for i in range(0, num_of_offers):
        guid = offer_registry.functions.channelsGuids(i).call()
        offer_channel = offer_registry.functions.guidToChannel(guid).call()
        channel_data = channel_to_dict(offer_channel)
        msig_address = channel_data['msig_address']
        offer_msig = bind_contract(web3, msig_address, offer_msig_artifact)
        opened_channel = offer_msig.functions.isOpen().call()
        if opened_channel:
            offers_opened.append({'guid': guid, 'address': msig_address})

    return success(offers_opened)

@offers.route('closed', methods=['GET'])
def get_closed():
    offers_closed = []
    web3 = web3_chains[chain]
    num_of_offers = offer_registry.functions.getNumberOfOffers().call()

    for i in range(0, num_of_offers):
        guid = offer_registry.functions.channelsGuids(i).call()
        offer_channel = offer_registry.functions.guidToChannel(guid).call()
        channel_data = channel_to_dict(offer_channel)
        msig_address = channel_data['msig_address']
        offer_msig = bind_contract(web3, msig_address, offer_msig_artifact)
        closed_channel = offer_msig.functions.isClosed().call()
        if closed_channel:
            offers_closed.append({'guid': guid, 'address': msig_address})

    return success(offers_closed)

@offers.route('myoffers', methods=['GET'])
def get_myoffers():
    web3 = web3_chains[chain]
    account = request.args.get('account')
    if not account or not web3.isAddress(account):
        return failure('Source account required', 401)

    my_offers = []

    num_of_offers = offer_registry.functions.getNumberOfOffers().call()

    for i in range(0, num_of_offers):
        guid = offer_registry.functions.channelsGuids(i).call()
        offer_channel = offer_registry.functions.guidToChannel(guid).call()
        channel_data = channel_to_dict(offer_channel)
        msig_address = channel_data['msig_address']
        offer_msig = bind_contract(web3, msig_address, offer_msig_artifact)
        expert = offer_msig.functions.expert().call()
        ambassador = offer_msig.functions.ambassador().call()
        if account is expert or account is ambassador:
            my_offers.append({'guid': guid, 'address': msig_address})

    return success(my_offers)
