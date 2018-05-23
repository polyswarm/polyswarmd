#!/usr/bin/env python3

import base58
import datetime
import json
import jsonschema
import os
import re
import requests
import sys
import uuid
import webbrowser

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from flask_sockets import Sockets
from gevent import pywsgi, sleep
from geventwebsocket.handler import WebSocketHandler
from jsonschema.exceptions import ValidationError
from web3 import Web3, HTTPProvider
from web3.middleware import geth_poa_middleware
from werkzeug.exceptions import default_exceptions, HTTPException
from werkzeug.utils import secure_filename

def whereami():
    if hasattr(sys, 'frozen') and sys.frozen in ('windows_exe', 'console_exe'):
        return os.path.dirname(os.path.abspath(sys.executable))
    else:
        return os.path.dirname(os.path.abspath(__file__))

load_dotenv(dotenv_path=os.path.join(whereami(), '.env'))

ETH_URI = os.environ.get('ETH_URI', 'http://localhost:8545')
IPFS_URI = os.environ.get('IPFS_URI', 'http://localhost:5001')

# Ok to use globals as gevent is single threaded
active_account = None
web3 = Web3(HTTPProvider(ETH_URI))
web3.middleware_stack.inject(geth_poa_middleware, layer=0)

def install_error_handlers(app):
    def make_json_error(e):
        response = jsonify(message=str(e))
        response.status_code = e.code if isinstance(e, HTTPException) else 500
        return response

    for code in default_exceptions.keys():
        app.register_error_handler(code, make_json_error)

# We need to do some weird stuff here to help flask find our files
network = os.environ.get('POLYSWARMD_NETWORK', None)
config_file = 'polyswarmd.cfg' if not network else 'polyswarmd.{}.cfg'.format(network)
app = Flask('polyswarmd', root_path=whereami(), instance_path=whereami())
app.config.from_pyfile(os.path.join(whereami(), config_file))
#If environment variables are set and of the right format, ignore the previous config
#and app.config to these values instead
if ("NECTAR_TOKEN_ADDRESS" in os.environ) and ("BOUNTY_REGISTRY_ADDRESS" in os.environ):
	if os.environ.get('NECTAR_TOKEN_ADDRESS'[0:2]) == "0x" and os.environ.get('BOUNTY_REGISTRY_ADDRESS')[0:2] == "0x":
		app.config['NECTAR_TOKEN_ADDRESS'] = os.environ.get('NECTAR_TOKEN_ADDRESS')
		app.config['BOUNTY_REGISTRY_ADDRESS'] = os.environ.get('BOUNTY_REGISTRY_ADDRESS')
install_error_handlers(app)
sockets = Sockets(app)

def bind_contract(address, artifact):
    with open(os.path.join(whereami(), artifact), 'r') as f:
        abi = json.load(f)['abi']

    return web3.eth.contract(address=web3.toChecksumAddress(address), abi=abi)

ZERO_ADDRESS = '0x0000000000000000000000000000000000000000'
nectar_token = bind_contract(
    app.config['NECTAR_TOKEN_ADDRESS'],
    'truffle/build/contracts/NectarToken.json'
)
bounty_registry = bind_contract(
    app.config['BOUNTY_REGISTRY_ADDRESS'],
    'truffle/build/contracts/BountyRegistry.json'
)

# Keep these in sync with the contract
BOUNTY_FEE = 62500000000000000
ASSERTION_FEE = 62500000000000000
BOUNTY_AMOUNT_MINIMUM = 62500000000000000
ASSERTION_BID_MINIMUM = 62500000000000000

def success(result=None):
    if result is not None:
        return jsonify({'status': 'OK', 'result': result}), 200
    else:
        return jsonify({'status': 'OK'}), 200

def failure(message, code=500):
    return jsonify({'status': 'FAIL', 'message': message}), code

def is_valid_ipfshash(ipfshash):
    # TODO: Further multihash validation
    try:
        return len(ipfshash) < 100 and base58.b58decode(ipfshash)
    except:
        pass

    return False

def list_artifacts(ipfshash):
    try:
        r = requests.get(IPFS_URI + '/api/v0/ls', params={'arg': ipfshash}, timeout=1)
        r.raise_for_status()
    except:
        return []

    links = [(l['Name'], l['Hash']) for l in r.json()['Objects'][0]['Links']]
    if not links:
        links = [('', r.json()['Objects'][0]['Hash'])]

    return links

@app.route('/artifacts', methods=['POST'])
def post_artifacts():
    files = [
        ('file', (f.filename, f, 'application/octet-stream'))
        for f in request.files.getlist(key='file')
    ]
    if len(files) > 256:
        return failure('Too many artifacts', 400)

    try:
        r = requests.post(
            IPFS_URI + '/api/v0/add', files=files,
            params={'wrap-with-directory': True}
        )
        r.raise_for_status()
    except:
        return failure("Could not add artifacts to IPFS", 400)

    ipfshash = json.loads(r.text.splitlines()[-1])['Hash']
    return success(ipfshash)

@app.route('/artifacts/<ipfshash>', methods=['GET'])
def get_artifacts_ipfshash(ipfshash):
    if not is_valid_ipfshash(ipfshash):
        return failure('Invalid IPFS hash', 400)

    artifacts = list_artifacts(ipfshash)
    if not artifacts:
        return failure('Could not locate IPFS resource', 404)
    if len(artifacts) > 256:
        return failure('Invalid IPFS resource, too many links', 400)

    return success([{'name': a[0], 'hash': a[1]} for a in artifacts])

@app.route('/artifacts/<ipfshash>/<int:id_>', methods=['GET'])
def get_artifacts_ipfshash_id(ipfshash, id_):
    if not is_valid_ipfshash(ipfshash):
        return failure('Invalid IPFS hash', 400)

    artifacts = list_artifacts(ipfshash)
    if not artifacts:
        return failure('Could not locate IPFS resource', 404)

    if id_ < 0 or id_ > 256 or id_ >= len(artifacts):
        return failure('Could not locate artifact ID', 404)

    artifact = artifacts[id_][1]

    try:
        r = requests.get(IPFS_URI + '/api/v0/cat', params={'arg': artifact}, timeout=1)
        r.raise_for_status()
    except:
        return failure("Could not locate IPFS resource", 404)

    return r.content

@app.route('/artifacts/<ipfshash>/<int:id_>/stat', methods=['GET'])
def get_artifacts_ipfshash_id_stat(ipfshash, id_):
    if not is_valid_ipfshash(ipfshash):
        return failure('Invalid IPFS hash', 400)

    artifacts = list_artifacts(ipfshash)
    if not artifacts:
        return failure('Could not locate IPFS resource', 404)

    if id_ < 0 or id_ > 256 or id_ >= len(artifacts):
        return failure('Could not locate artifact ID', 404)

    artifact = artifacts[id_][1]

    try:
        r = requests.get(IPFS_URI + '/api/v0/object/stat', params={'arg': artifact})
        r.raise_for_status()
    except:
        return failure("Could not locate IPFS resource", 400)

    # Convert stats to snake_case
    stats = {re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', k).lower(): v for k, v in r.json().items()}
    stats['name'] = artifacts[id_][0]

    return success(stats)

def wait_for_receipt(tx):
    while True:
        receipt = web3.eth.getTransactionReceipt(tx)
        if receipt:
            return receipt
        sleep(1)

def check_transaction(tx):
    receipt = wait_for_receipt(tx)
    return receipt.status == 1

def bool_list_to_int(bs):
    return sum([1 << n if b else 0 for n, b in enumerate(bs)])

def int_to_bool_list(i):
    s = format(i, 'b')
    return [x == '1' for x in s[::-1]]

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

@app.route('/bounties', methods=['POST'])
def post_bounties():
    if active_account is None:
        return failure('Account unlock required', 401)

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

    if amount < BOUNTY_AMOUNT_MINIMUM:
        return failure('Invalid bounty amount', 400)

    if not is_valid_ipfshash(artifactURI):
        return failure('Invalid artifact URI (should be IPFS hash)', 400)

    approveAmount = amount + BOUNTY_FEE

    tx = nectar_token.functions.approve(
        bounty_registry.address, approveAmount
    ).transact({'from': active_account, 'gasLimit': 200000})
    if not check_transaction(tx):
        return failure('Approve transaction failed, verify parameters and try again', 400)

    tx = bounty_registry.functions.postBounty(
        guid.int, amount, artifactURI, durationBlocks
    ).transact({'from': active_account, 'gasLimit': 200000})
    if not check_transaction(tx):
        return failure('Post bounty transaction failed, verify parameters and try again', 400)

    receipt = web3.eth.getTransactionReceipt(tx)
    processed = bounty_registry.events.NewBounty().processReceipt(receipt)
    if len(processed) == 0:
        return failure('Invalid transaction receipt, no events emitted. Check contract addresses', 400)
    new_bounty_event = processed[0]['args']
    return success(new_bounty_event_to_dict(new_bounty_event))

# TODO: Caching layer for this
@app.route('/bounties', methods=['GET'])
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
@app.route('/bounties/active', methods=['GET'])
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
@app.route('/bounties/pending', methods=['GET'])
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

@app.route('/bounties/<uuid:guid>', methods=['GET'])
def get_bounties_guid(guid):
    bounty = bounty_to_dict(bounty_registry.functions.bountiesByGuid(guid.int).call())
    if bounty['author'] == ZERO_ADDRESS:
        return failure('Bounty not found', 404)
    else:
        return success(bounty)

@app.route('/bounties/<uuid:guid>/settle', methods=['POST'])
def post_bounties_guid_settle(guid):
    if active_account is None:
        return failure('Account unlock required', 401)

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

    tx = bounty_registry.functions.settleBounty(
        guid.int, verdicts
    ).transact({'from': active_account, 'gasLimit': 1000000})
    if not check_transaction(tx):
        return failure('Settle bounty transaction failed, verify parameters and try again', 400)

    receipt = web3.eth.getTransactionReceipt(tx)
    processed = bounty_registry.events.NewVerdict().processReceipt(receipt)
    if len(processed) == 0:
        return failure('Invalid transaction receipt, no events emitted. Check contract addresses', 400)
    new_verdict_event = processed[0]['args']
    return success(new_verdict_event_to_dict(new_verdict_event))

@app.route('/bounties/<uuid:guid>/assertions', methods=['POST'])
def post_bounties_guid_assertions(guid):
    if active_account is None:
        return failure('Account unlock required', 401)

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

    if bid < ASSERTION_BID_MINIMUM:
        return failure('Invalid assertion bid', 400)

    approveAmount = bid + ASSERTION_FEE

    tx = nectar_token.functions.approve(
        bounty_registry.address, approveAmount
    ).transact({'from': active_account, 'gasLimit': 200000})
    if not check_transaction(tx):
        return failure('Approve transaction failed, verify parameters and try again', 400)

    tx = bounty_registry.functions.postAssertion(
        guid.int, bid, mask, verdicts, metadata
    ).transact({'from': active_account, 'gasLimit': 200000})
    if not check_transaction(tx):
        return failure('Post assertion transaction failed, verify parameters and try again', 400)

    receipt = web3.eth.getTransactionReceipt(tx)
    processed = bounty_registry.events.NewAssertion().processReceipt(receipt)
    if len(processed) == 0:
        return failure('Invalid transaction receipt, no events emitted. Check contract addresses', 400)
    new_assertion_event = processed[0]['args']
    return success(new_assertion_event_to_dict(new_assertion_event))

@app.route('/bounties/<uuid:guid>/assertions', methods=['GET'])
def get_bounties_guid_assertions(guid):
    num_assertions = bounty_registry.functions.getNumberOfAssertions(guid.int).call()
    assertions = []
    for i in range(num_assertions):
        assertion = assertion_to_dict(bounty_registry.functions.assertionsByGuid(guid.int, i).call())
        assertions.append(assertion)

    return success(assertions)

@app.route('/bounties/<uuid:guid>/assertions/<int:id_>', methods=['GET'])
def get_bounties_guid_assertions_id(guid, id_):
    try:
        return success(assertion_to_dict(bounty_registry.functions.assertionsByGuid(guid.int, id_).call()))
    except:
        return failure('Assertion not found', 404)

@app.route('/accounts', methods=['POST'])
def post_accounts():
    schema = {
        'type': 'object',
        'properties': {
            'password': {
                'type': 'string',
                'minLength': 1,
                'maxLength': 1024,
            },
        },
        'required': ['password'],
    }

    body = request.get_json()
    try:
        jsonschema.validate(body, schema)
    except ValidationError as e:
        return failure('Invalid JSON: ' + e.message, 400)

    password = body['password']
    return success(web3.personal.newAccount(password))

@app.route('/accounts', methods=['GET'])
def get_accounts():
    return success(web3.personal.listAccounts)

@app.route('/accounts/active', methods=['GET'])
def get_accounts_active():
    if active_account:
        return success(active_account)
    else:
        return failure('No active account, unlock required', 401)

@app.route('/accounts/<address>/unlock', methods=['POST'])
def post_accounts_address_unlock(address):
    global active_account
    if not web3.isAddress(address):
        return failure('Invalid address', 400)

    schema = {
        'type': 'object',
        'properties': {
            'password': {
                'type': 'string',
                'minLength': 1,
                'maxLength': 1024,
            },
        },
        'required': ['password'],
    }

    body = request.get_json()
    try:
        jsonschema.validate(body, schema)
    except ValidationError as e:
        return failure('Invalid JSON: ' + e.message, 400)

    address = web3.toChecksumAddress(address)
    if web3.personal.unlockAccount(address, body['password'], 9223372036):
        active_account = address
        return success(active_account)
    else:
        return failure('Incorrect password', 401)

@app.route('/accounts/<address>/lock', methods=['POST'])
def post_accounts_address_lock(address):
    global active_account
    if not web3.isAddress(address):
        return failure('Invalid address', 400)

    address = web3.toChecksumAddress(address)
    if active_account == address:
        web3.personal.lockAccount(address)
        active_account = None
        return success()
    else:
        return failure('Account not unlocked', 401)

@app.route('/accounts/<address>/balance/eth', methods=['GET'])
def post_accounts_address_balance_eth(address):
    if not web3.isAddress(address):
        return failure('Invalid address', 400)

    address = web3.toChecksumAddress(address)
    return success(str(web3.eth.getBalance(address)))

@app.route('/accounts/<address>/balance/nct', methods=['GET'])
def post_accounts_address_balance_nct(address):
    if not web3.isAddress(address):
        return failure('Invalid address', 400)

    address = web3.toChecksumAddress(address)
    return success(str(nectar_token.functions.balanceOf(address).call()))

@app.route('/syncing', methods=['GET'])
def get_syncing():
    if not web3.eth.syncing:
        return success(False)
    else:
        return success(dict(web3.eth.syncing))

@sockets.route('/events')
def events(ws):
    block_filter = web3.eth.filter('latest')
    bounty_filter = bounty_registry.eventFilter('NewBounty')
    assertion_filter = bounty_registry.eventFilter('NewAssertion')
    verdict_filter = bounty_registry.eventFilter('NewVerdict')

    try:
        while not ws.closed:
            for event in block_filter.get_new_entries():
                ws.send(json.dumps({
                    'event': 'block',
                    'data': {
                        'number': web3.eth.blockNumber,
                    },
                }))

            for event in bounty_filter.get_new_entries():
                ws.send(json.dumps({
                    'event': 'bounty',
                    'data': new_bounty_event_to_dict(event.args),
                }))

            for event in assertion_filter.get_new_entries():
                ws.send(json.dumps({
                    'event': 'assertion',
                    'data': new_assertion_event_to_dict(event.args),
                }))

            for event in verdict_filter.get_new_entries():
                ws.send(json.dumps({
                    'event': 'verdict',
                    'data': new_verdict_event_to_dict(event.args),
                }))

            sleep(1)
    except:
        return

@app.before_request
def before_request():
    print(datetime.datetime.now(), request.method, request.path)

def main():
    server = pywsgi.WSGIServer(('', 31337), app, handler_class=WebSocketHandler)
    server.serve_forever()

if __name__ == '__main__':
    main()
