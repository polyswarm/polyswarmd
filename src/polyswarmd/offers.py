import uuid
import json
import jsonschema
from jsonschema.exceptions import ValidationError
from flask import Blueprint, g, request
from websocket import create_connection
from polyswarmd.eth import web3 as web3_chains, build_transaction, \
        nectar_token, offer_registry, bind_contract, offer_msig_artifact, offer_lib
from polyswarmd.response import success, failure
from polyswarmd.utils import channel_to_dict, validate_ws_url, dict_to_state, to_padded_hex, bool_list_to_int

chain = 'home'  # only on home chain
offers = Blueprint('offers', __name__)


@offers.route('', methods=['POST'])
def post_create_offer_channel():
    web3 = web3_chains[chain]
    account = web3.toChecksumAddress(g.eth_address)

    base_nonce = int(
        request.args.get('base_nonce', web3.eth.getTransactionCount(account)))

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
        },
        'required': ['ambassador', 'expert', 'settlementPeriodLength'],
    }

    try:
        jsonschema.validate(body, schema)
    except ValidationError as e:
        return failure('Invalid JSON: ' + e.message)

    guid = uuid.uuid4()
    ambassador = web3.toChecksumAddress(body['ambassador'])
    expert = web3.toChecksumAddress(body['expert'])
    settlement_period_length = body['settlementPeriodLength']

    transactions = [
        build_transaction(
            offer_registry.functions.initializeOfferChannel(
                guid.int, ambassador, expert, settlement_period_length), chain,
            base_nonce),
    ]

    return success({'transactions': transactions})


@offers.route('/<uuid:guid>/uri', methods=['POST'])
def post_uri(guid):
    web3 = web3_chains[chain]
    offer_channel = channel_to_dict(
        offer_registry.functions.guidToChannel(guid.int).call())
    msig_address = offer_channel['msig_address']
    offer_msig = bind_contract(web3, msig_address, offer_msig_artifact)
    account = web3.toChecksumAddress(g.eth_address)

    base_nonce = int(
        request.args.get('base_nonce', web3.eth.getTransactionCount(account)))

    body = request.get_json()

    schema = {
        'type': 'object',
        'properties': {
            'websocketUri': {
                'type': 'string',
                'minLength': 1,
                'maxLength': 32
            }
        },
        'required': ['websocketUri'],
    }

    try:
        jsonschema.validate(body, schema)
    except ValidationError as e:
        return failure('Invalid JSON: ' + e.message)

    websocket_uri = body['websocketUri']

    transactions = [
        build_transaction(
            offer_msig.functions.setCommunicationUri(
                web3.toHex(text=websocket_uri)),
            chain,
            base_nonce),
    ]

    return success({'transactions': transactions})


@offers.route('/<uuid:guid>/open', methods=['POST'])
def post_open(guid):
    web3 = web3_chains[chain]
    offer_channel = channel_to_dict(
        offer_registry.functions.guidToChannel(guid.int).call())
    msig_address = offer_channel['msig_address']
    offer_msig = bind_contract(web3, msig_address, offer_msig_artifact)
    account = web3.toChecksumAddress(g.eth_address)

    base_nonce = int(
        request.args.get('base_nonce', web3.eth.getTransactionCount(account)))

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
            },
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

    approve_amount = offer_lib.functions.getBalanceA(state).call()

    transactions = [
        build_transaction(
            nectar_token['home'].functions.approve(
                msig_address, approve_amount), chain, base_nonce),
        build_transaction(
            offer_msig.functions.openAgreement(to_padded_hex(state), v, to_padded_hex(r), to_padded_hex(s)), chain,
            base_nonce + 1),
    ]

    return success({'transactions': transactions})


@offers.route('/<uuid:guid>/cancel', methods=['POST'])
def post_cancel(guid):
    web3 = web3_chains[chain]
    offer_channel = channel_to_dict(
        offer_registry.functions.guidToChannel(guid.int).call())
    msig_address = offer_channel['msig_address']
    offer_msig = bind_contract(web3, msig_address, offer_msig_artifact)
    account = web3.toChecksumAddress(g.eth_address)

    base_nonce = int(
        request.args.get('base_nonce', web3.eth.getTransactionCount(account)))

    transactions = [
        build_transaction(offer_msig.functions.cancel(), chain, base_nonce),
    ]

    return success({'transactions': transactions})


@offers.route('/<uuid:guid>/join', methods=['POST'])
def post_join(guid):
    web3 = web3_chains[chain]
    offer_channel = channel_to_dict(
        offer_registry.functions.guidToChannel(guid.int).call())
    msig_address = offer_channel['msig_address']
    offer_msig = bind_contract(web3, msig_address, offer_msig_artifact)
    account = web3.toChecksumAddress(g.eth_address)

    base_nonce = int(
        request.args.get('base_nonce', web3.eth.getTransactionCount(account)))

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
            },
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

    transactions = [
        build_transaction(
            offer_msig.functions.joinAgreement(state, v, to_padded_hex(r), to_padded_hex(s)), chain,
            base_nonce),
    ]

    return success({'transactions': transactions})


@offers.route('/<uuid:guid>/close', methods=['POST'])
def post_close(guid):
    web3 = web3_chains[chain]
    offer_channel = channel_to_dict(
        offer_registry.functions.guidToChannel(guid.int).call())
    msig_address = offer_channel['msig_address']
    offer_msig = bind_contract(web3, msig_address, offer_msig_artifact)
    account = web3.toChecksumAddress(g.eth_address)

    base_nonce = int(
        request.args.get('base_nonce', web3.eth.getTransactionCount(account)))

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
            },
        },
        'required': ['state', 'r', 'v', 's'],
    }

    try:
        jsonschema.validate(body, schema)
    except ValidationError as e:
        return failure('Invalid JSON: ' + e.message)

    state = web3.toBytes(hexstr=body['state'])
    v = body['v']
    r = list(map(lambda s: web3.toBytes(hexstr=s), body['r']))
    s = list(map(lambda s: web3.toBytes(hexstr=s), body['s']))

    transactions = [
        build_transaction(
            offer_msig.functions.closeAgreement(state, v, r, s), chain,
            base_nonce),
    ]

    return success({'transactions': transactions})


# for closing a challenged state with a timeout
@offers.route('/<uuid:guid>/closeChallenged', methods=['POST'])
def post_close_challenged(guid):
    web3 = web3_chains[chain]
    offer_channel = channel_to_dict(
        offer_registry.functions.guidToChannel(guid.int).call())
    msig_address = offer_channel['msig_address']
    offer_msig = bind_contract(web3, msig_address, offer_msig_artifact)
    account = web3.toChecksumAddress(g.eth_address)

    base_nonce = int(
        request.args.get('base_nonce', web3.eth.getTransactionCount(account)))

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
            },
        },
        'required': ['state', 'r', 'v', 's'],
    }

    try:
        jsonschema.validate(body, schema)
    except ValidationError as e:
        return failure('Invalid JSON: ' + e.message)

    state = web3.toBytes(hexstr=body['state'])
    v = body['v']
    r = list(map(lambda s: web3.toBytes(hexstr=s), body['r']))
    s = list(map(lambda s: web3.toBytes(hexstr=s), body['s']))

    transactions = [
        build_transaction(
            offer_msig.functions.closeAgreementWithTimeout(state, v, r, s),
            chain, base_nonce),
    ]

    return success({'transactions': transactions})


@offers.route('/<uuid:guid>/settle', methods=['POST'])
def post_settle(guid):
    web3 = web3_chains[chain]
    offer_channel = channel_to_dict(
        offer_registry.functions.guidToChannel(guid.int).call())
    msig_address = offer_channel['msig_address']
    offer_msig = bind_contract(web3, msig_address, offer_msig_artifact)
    account = web3.toChecksumAddress(g.eth_address)

    base_nonce = int(
        request.args.get('base_nonce', web3.eth.getTransactionCount(account)))

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
            },
        },
        'required': ['state', 'r', 'v', 's'],
    }

    try:
        jsonschema.validate(body, schema)
    except ValidationError as e:
        return failure('Invalid JSON: ' + e.message)

    state = web3.toBytes(hexstr=body['state'])
    v = body['v']
    r = list(map(lambda s: web3.toBytes(hexstr=s), body['r']))
    s = list(map(lambda s: web3.toBytes(hexstr=s), body['s']))

    transactions = [
        build_transaction(
            offer_msig.functions.startSettle(state, v, r, s), chain,
            base_nonce),
    ]

    return success({'transactions': transactions})


@offers.route('/state', methods=['POST'])
def create_state():

    body = request.get_json()

    schema = {
        'type':
        'object',
        'properties': {
            'close_flag': {
                'type': 'integer',
                'minimum': 0,
                'maximum': 1
            },
            'nonce': {
                'type': 'integer',
                'minimum': 0,
            },
            'ambassador': {
                'type': 'string',
                'minLength': 1,
            },
            'expert': {
                'type': 'string',
                'minLength': 1,
            },
            'msig_address': {
                'type': 'string',
                'minLength': 1,
            },
            'ambassador_balance': {
                'type': 'integer',
                'minimum': 0,
            },
            'expert_balance': {
                'type': 'integer',
                'minimum': 0,
            },
            'guid': {
                'type': 'string',
                'minLength': 1,
            },
            'offer_amount': {
                'type': 'integer',
                'minimum': 0,
            },
            'artifact_hash': {
                'type': 'string',
                'minimum': 0,
            },
            'ipfs_hash': {
                'type': 'string',
                'minimum': 0,
            },
            'engagement_deadline': {
                'type': 'string',
                'minimum': 0,
            },
            'assertion_deadline': {
                'type': 'string',
                'minLength': 1
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
            'meta_data': {
                'type': 'string',
                'minLength': 1
            }
        },
        'required': [
            'close_flag', 'nonce', 'expert', 'msig_address',
            'ambassador_balance', 'expert_balance', 'guid', 'offer_amount'
        ],
    }

    try:
        jsonschema.validate(body, schema)
    except ValidationError as e:
        return failure('Invalid JSON: ' + e.message)

    body['token_address'] = str(nectar_token[chain].address)

    if 'verdicts' in body and not 'mask' in body or 'mask' in body and not 'verdicts' in body:
        return failure('Invalid JSON: Both `verdicts` and `mask` properties must be sent')
    elif 'verdicts' in body and 'mask' in body:    
        body['verdicts'] = bool_list_to_int(body['verdicts'])
        body['mask'] = bool_list_to_int(body['mask'])

    return success({'state': dict_to_state(body)})


@offers.route('/<uuid:guid>/challenge', methods=['POST'])
def post_challange(guid):
    web3 = web3_chains[chain]
    offer_channel = channel_to_dict(
        offer_registry.functions.guidToChannel(guid.int).call())
    msig_address = offer_channel['msig_address']
    offer_msig = bind_contract(web3, msig_address, offer_msig_artifact)
    account = web3.toChecksumAddress(g.eth_address)

    base_nonce = int(
        request.args.get('base_nonce', web3.eth.getTransactionCount(account)))

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
            },
        },
        'required': ['state', 'r', 'v', 's'],
    }

    try:
        jsonschema.validate(body, schema)
    except ValidationError as e:
        return failure('Invalid JSON: ' + e.message)

    state = web3.toBytes(hexstr=body['state'])
    v = body['v']
    r = list(map(lambda s: web3.toBytes(hexstr=s), body['r']))
    s = list(map(lambda s: web3.toBytes(hexstr=s), body['s']))

    transactions = [
        build_transaction(
            offer_msig.functions.challengeSettle(state, v, r, s), chain,
            base_nonce),
    ]

    return success({'transactions': transactions})

@offers.route('/<uuid:guid>', methods=['GET'])
def get_channel_address(guid):
    offer_channel = offer_registry.functions.guidToChannel(guid.int).call()

    return success({'offer_channel': channel_to_dict(offer_channel)})


@offers.route('/<uuid:guid>/settlementPeriod', methods=['GET'])
def get_settlement_period(guid):
    web3 = web3_chains[chain]
    offer_channel = offer_registry.functions.guidToChannel(guid.int).call()
    channel_data = channel_to_dict(offer_channel)
    offer_msig = bind_contract(web3, channel_data['msig_address'],
                               offer_msig_artifact)

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

    if not validate_ws_url(socket_uri):
        return failure(
            'Contract does not have a valid websocket uri',
            400)
        
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
    account = web3.toChecksumAddress(g.eth_address)

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
        if account == expert or account == ambassador:
            my_offers.append({'guid': guid, 'address': msig_address})

    return success(my_offers)
