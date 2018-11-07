import uuid
import jsonschema
import logging
from jsonschema.exceptions import ValidationError
from flask import Blueprint, g, request
from polyswarmd.chains import chain
from polyswarmd.eth import build_transaction
from polyswarmd.response import success, failure
from polyswarmd.utils import channel_to_dict, validate_ws_url, dict_to_state, to_padded_hex, bool_list_to_int

logger = logging.getLogger(__name__)
offers = Blueprint('offers', __name__)


@offers.route('', methods=['POST'])
@chain(chain_name='home')
def post_create_offer_channel():
    account = g.chain.w3.toChecksumAddress(g.eth_address)
    base_nonce = int(request.args.get('base_nonce', g.chain.w3.eth.getTransactionCount(account)))

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
    ambassador = g.chain.w3.toChecksumAddress(body['ambassador'])
    expert = g.chain.w3.toChecksumAddress(body['expert'])
    settlement_period_length = body['settlementPeriodLength']

    transactions = [
        build_transaction(
            g.chain.offer_registry.contract.functions.initializeOfferChannel(guid.int, ambassador, expert,
                                                                             settlement_period_length),
            base_nonce),
    ]

    return success({'transactions': transactions})


@offers.route('/<uuid:guid>/uri', methods=['POST'])
@chain(chain_name='home')
def post_uri(guid):
    offer_channel = channel_to_dict(g.chain.offer_registry.contract.functions.guidToChannel(guid.int).call())
    msig_address = offer_channel['msig_address']
    offer_msig = g.chain.offer_multisig.bind(msig_address)
    account = g.chain.w3.toChecksumAddress(g.eth_address)
    base_nonce = int(request.args.get('base_nonce', g.chain.w3.eth.getTransactionCount(account)))

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
        build_transaction(offer_msig.functions.setCommunicationUri(g.chain.w3.toHex(text=websocket_uri)), base_nonce),
    ]

    return success({'transactions': transactions})


@offers.route('/<uuid:guid>/open', methods=['POST'])
@chain(chain_name='home')
def post_open(guid):
    offer_channel = channel_to_dict(
        g.chain.offer_registry.contract.functions.guidToChannel(guid.int).call())
    msig_address = offer_channel['msig_address']
    offer_msig = g.chain.offer_multisig.bind(msig_address)
    account = g.chain.w3.toChecksumAddress(g.eth_address)
    base_nonce = int(request.args.get('base_nonce', g.chain.w3.eth.getTransactionCount(account)))

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

    approve_amount = g.chain.offer_lib.contract.functions.getBalanceA(state).call()

    transactions = [
        build_transaction(g.chain.nectar_token.contract.functions.approve(msig_address, approve_amount), base_nonce),
        build_transaction(
            offer_msig.functions.openAgreement(to_padded_hex(state), v, to_padded_hex(r), to_padded_hex(s)),
            base_nonce + 1),
    ]

    return success({'transactions': transactions})


@offers.route('/<uuid:guid>/cancel', methods=['POST'])
@chain(chain_name='home')
def post_cancel(guid):
    offer_channel = channel_to_dict(
        g.chain.offer_registry.contract.functions.guidToChannel(guid.int).call())
    msig_address = offer_channel['msig_address']
    offer_msig = g.chain.offer_multisig.bind(msig_address)
    account = g.chain.w3.toChecksumAddress(g.eth_address)
    base_nonce = int(request.args.get('base_nonce', g.chain.w3.eth.getTransactionCount(account)))

    transactions = [
        build_transaction(offer_msig.functions.cancel(), base_nonce),
    ]

    return success({'transactions': transactions})


@offers.route('/<uuid:guid>/join', methods=['POST'])
@chain(chain_name='home')
def post_join(guid):
    offer_channel = channel_to_dict(g.chain.offer_registry.contract.functions.guidToChannel(guid.int).call())
    msig_address = offer_channel['msig_address']
    offer_msig = g.chain.offer_multisig.bind(msig_address)
    account = g.chain.w3.toChecksumAddress(g.eth_address)
    base_nonce = int(request.args.get('base_nonce', g.chain.w3.eth.getTransactionCount(account)))

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
        build_transaction(offer_msig.functions.joinAgreement(state, v, to_padded_hex(r), to_padded_hex(s)), base_nonce),
    ]

    return success({'transactions': transactions})


@offers.route('/<uuid:guid>/close', methods=['POST'])
@chain(chain_name='home')
def post_close(guid):
    offer_channel = channel_to_dict(g.chain.offer_registry.contract.functions.guidToChannel(guid.int).call())
    msig_address = offer_channel['msig_address']
    offer_msig = g.chain.offer_multisig.bind(msig_address)
    account = g.chain.w3.toChecksumAddress(g.eth_address)
    base_nonce = int(request.args.get('base_nonce', g.chain.w3.eth.getTransactionCount(account)))

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

    state = g.chain.w3.toBytes(hexstr=body['state'])
    v = body['v']
    r = list(map(lambda s: g.chain.w3.toBytes(hexstr=s), body['r']))
    s = list(map(lambda s: g.chain.w3.toBytes(hexstr=s), body['s']))

    transactions = [
        build_transaction(offer_msig.functions.closeAgreement(state, v, r, s), base_nonce),
    ]

    return success({'transactions': transactions})


# for closing a challenged state with a timeout
@offers.route('/<uuid:guid>/closeChallenged', methods=['POST'])
@chain(chain_name='home')
def post_close_challenged(guid):
    offer_channel = channel_to_dict(g.chain.offer_registry.contract.functions.guidToChannel(guid.int).call())
    msig_address = offer_channel['msig_address']
    offer_msig = g.chain.offer_multisig.bind(msig_address)
    account = g.chain.w3.toChecksumAddress(g.eth_address)
    base_nonce = int(request.args.get('base_nonce', g.chain.w3.eth.getTransactionCount(account)))

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

    state = g.chain.w3.toBytes(hexstr=body['state'])
    v = body['v']
    r = list(map(lambda s: g.chain.w3.toBytes(hexstr=s), body['r']))
    s = list(map(lambda s: g.chain.w3.toBytes(hexstr=s), body['s']))

    transactions = [
        build_transaction(offer_msig.functions.closeAgreementWithTimeout(state, v, r, s), base_nonce),
    ]

    return success({'transactions': transactions})


@offers.route('/<uuid:guid>/settle', methods=['POST'])
@chain(chain_name='home')
def post_settle(guid):
    offer_channel = channel_to_dict(
        g.chain.offer_registry.contract.functions.guidToChannel(guid.int).call())
    msig_address = offer_channel['msig_address']
    offer_msig = g.chain.offer_multisig.bind(msig_address)
    account = g.chain.w3.toChecksumAddress(g.eth_address)
    base_nonce = int(request.args.get('base_nonce', g.chain.w3.eth.getTransactionCount(account)))

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

    state = g.chain.w3.toBytes(hexstr=body['state'])
    v = body['v']
    r = list(map(lambda s: g.chain.w3.toBytes(hexstr=s), body['r']))
    s = list(map(lambda s: g.chain.w3.toBytes(hexstr=s), body['s']))

    transactions = [
        build_transaction(offer_msig.functions.startSettle(state, v, r, s), base_nonce),
    ]

    return success({'transactions': transactions})


@offers.route('/state', methods=['POST'])
@chain(chain_name='home')
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

    body['token_address'] = str(g.chain.nectar_token.address)

    if 'verdicts' in body and not 'mask' in body or 'mask' in body and not 'verdicts' in body:
        return failure('Invalid JSON: Both `verdicts` and `mask` properties must be sent')
    elif 'verdicts' in body and 'mask' in body:
        body['verdicts'] = bool_list_to_int(body['verdicts'])
        body['mask'] = bool_list_to_int(body['mask'])

    return success({'state': dict_to_state(body)})


@offers.route('/<uuid:guid>/challenge', methods=['POST'])
@chain(chain_name='home')
def post_challange(guid):
    offer_channel = channel_to_dict(g.chain.offer_registry.contract.functions.guidToChannel(guid.int).call())
    msig_address = offer_channel['msig_address']
    offer_msig = g.chain.offer_multisig.bind(msig_address)
    account = g.chain.w3.toChecksumAddress(g.eth_address)
    base_nonce = int(request.args.get('base_nonce', g.chain.w3.eth.getTransactionCount(account)))

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

    state = g.chain.w3.toBytes(hexstr=body['state'])
    v = body['v']
    r = list(map(lambda s: g.chain.w3.toBytes(hexstr=s), body['r']))
    s = list(map(lambda s: g.chain.w3.toBytes(hexstr=s), body['s']))

    transactions = [
        build_transaction(offer_msig.functions.challengeSettle(state, v, r, s), base_nonce),
    ]

    return success({'transactions': transactions})


@offers.route('/<uuid:guid>', methods=['GET'])
@chain(chain_name='home')
def get_channel_address(guid):
    offer_channel = g.chain.offer_registry.contract.functions.guidToChannel(guid.int).call()
    return success({'offer_channel': channel_to_dict(offer_channel)})


@offers.route('/<uuid:guid>/settlementPeriod', methods=['GET'])
@chain(chain_name='home')
def get_settlement_period(guid):
    offer_channel = g.chain.offer_registry.contract.functions.guidToChannel(guid.int).call()
    channel_data = channel_to_dict(offer_channel)
    msig_address = channel_data['msig_address']
    offer_msig = g.chain.offer_multisig.bind(msig_address)

    settlement_period_end = offer_msig.functions.settlementPeriodEnd().call()

    return success({'settlementPeriodEnd': settlement_period_end})


@offers.route('/<uuid:guid>/websocket', methods=['GET'])
@chain(chain_name='home')
def get_websocket(guid):
    offer_channel = g.chain.offer_registry.contract.functions.guidToChannel(guid.int).call()
    channel_data = channel_to_dict(offer_channel)
    msig_address = channel_data['msig_address']
    offer_msig = g.chain.offer_multisig.bind(msig_address)
    socket_uri = offer_msig.functions.websocketUri().call()

    # TODO find a better way than replace
    socket_uri = g.chain.w3.toText(socket_uri).replace('\u0000', '')

    if not validate_ws_url(socket_uri):
        return failure(
            'Contract does not have a valid websocket uri',
            400)

    return success({'websocket': socket_uri})


@offers.route('pending', methods=['GET'])
@chain(chain_name='home')
def get_pending():
    offers_pending = []
    num_of_offers = g.chain.offer_registry.contract.functions.getNumberOfOffers().call()

    for i in range(0, num_of_offers):
        guid = g.chain.offer_registry.contract.functions.channelsGuids(i).call()
        offer_channel = g.chain.offer_registry.contract.functions.guidToChannel(guid).call()
        channel_data = channel_to_dict(offer_channel)
        msig_address = channel_data['msig_address']
        offer_msig = g.chain.offer_multisig.bind(msig_address)
        pending_channel = offer_msig.functions.isPending().call()
        if pending_channel:
            offers_pending.append({'guid': guid, 'address': msig_address})

    return success(offers_pending)


@offers.route('opened', methods=['GET'])
@chain(chain_name='home')
def get_opened():
    offers_opened = []
    num_of_offers = g.chain.offer_registry.contract.functions.getNumberOfOffers().call()

    for i in range(0, num_of_offers):
        guid = g.chain.offer_registry.contract.functions.channelsGuids(i).call()
        offer_channel = g.chain.offer_registry.contract.functions.guidToChannel(guid).call()
        channel_data = channel_to_dict(offer_channel)
        msig_address = channel_data['msig_address']
        offer_msig = g.chain.offer_multisig.bind(msig_address)
        opened_channel = offer_msig.functions.isOpen().call()
        if opened_channel:
            offers_opened.append({'guid': guid, 'address': msig_address})

    return success(offers_opened)


@offers.route('closed', methods=['GET'])
@chain(chain_name='home')
def get_closed():
    offers_closed = []
    num_of_offers = g.chain.offer_registry.contract.functions.getNumberOfOffers().call()

    for i in range(0, num_of_offers):
        guid = g.chain.offer_registry.contract.functions.channelsGuids(i).call()
        offer_channel = g.chain.offer_registry.contract.functions.guidToChannel(guid).call()
        channel_data = channel_to_dict(offer_channel)
        msig_address = channel_data['msig_address']
        offer_msig = g.chain.offer_multisig.bind(msig_address)
        closed_channel = offer_msig.functions.isClosed().call()
        if closed_channel:
            offers_closed.append({'guid': guid, 'address': msig_address})

    return success(offers_closed)


@offers.route('myoffers', methods=['GET'])
@chain(chain_name='home')
def get_myoffers():
    account = g.chain.w3.toChecksumAddress(g.eth_address)

    my_offers = []
    num_of_offers = g.chain.offer_registry.contract.functions.getNumberOfOffers().call()

    for i in range(0, num_of_offers):
        guid = g.chain.offer_registry.contract.functions.channelsGuids(i).call()
        offer_channel = g.chain.offer_registry.contract.functions.guidToChannel(guid).call()
        channel_data = channel_to_dict(offer_channel)
        msig_address = channel_data['msig_address']
        offer_msig = g.chain.offer_multisig.bind(msig_address)
        expert = offer_msig.functions.expert().call()
        ambassador = offer_msig.functions.ambassador().call()
        if account == expert or account == ambassador:
            my_offers.append({'guid': guid, 'address': msig_address})

    return success(my_offers)
