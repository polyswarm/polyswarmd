#! /usr/bin/env python3

import json
import jsonschema
import sys
import uuid

import base58
import requests
from flask import Flask, jsonify, request
from flask_sockets import Sockets
from gevent import pywsgi, sleep
from geventwebsocket.handler import WebSocketHandler
from web3 import Web3, HTTPProvider
from werkzeug.exceptions import default_exceptions, HTTPException
from werkzeug.utils import secure_filename

def install_error_handlers(app):
    def make_json_error(e):
        response = jsonify(message=str(e))
        response.status_code = e.code if isinstance(e, HTTPException) else 500
        return response

    for code in default_exceptions.keys():
        app.register_error_handler(code, make_json_error)

app = Flask('polyswarmd')
install_error_handlers(app)
sockets = Sockets(app)

# TEMP
IPFS_URI = 'http://localhost:5001'
ETH_URI = 'http://localhost:8545'

# Ok to use globals as gevent is single threaded
web3 = Web3(HTTPProvider(ETH_URI))
active_account = None

def bind_contract(address, artifact):
    with open(artifact, 'r') as f:
        abi = json.load(f)['abi']

    return web3.eth.contract(address=web3.toChecksumAddress(address), abi=abi) 

NECTAR_TOKEN_ADDRESS = '0xf3ac3484e2f7262e55e83c85a3f6f0fd26b0ffed'
BOUNTY_REGISTRY_ADDRESS = '0x7f49ed4680103019ce2849e747a371bc83467029'
nectar_token = bind_contract(NECTAR_TOKEN_ADDRESS, 'truffle/build/contracts/NectarToken.json')
bounty_registry = bind_contract(BOUNTY_REGISTRY_ADDRESS, 'truffle/build/contracts/BountyRegistry.json')

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
    r = requests.get(IPFS_URI + '/api/v0/ls', params={'arg': ipfshash})
    if r.status_code != 200:
        return []

    links = [l['Hash'] for l in r.json()['Objects'][0]['Links']]
    if not links:
        links = [r.json()['Objects'][0]['Hash']]

    return links

@app.route('/artifacts', methods=['POST'])
def post_artifacts():
    files = [('file', (f.filename, f, 'application/octet-stream')) for f in request.files.getlist(key='file')]
    r = requests.post(IPFS_URI + '/api/v0/add', files=files, params={'wrap-with-directory': True})
    if r.status_code != 200:
        return failure(r.text, r.status_code)

    ipfshash = json.loads(r.text.splitlines()[-1])['Hash']
    return success(ipfshash)

@app.route('/artifacts/<ipfshash>', methods=['GET'])
def get_artifacts_ipfshash(ipfshash):
    if not is_valid_ipfshash(ipfshash):
        return failure('Invalid IPFS hash', 400)

    artifacts = list_artifacts(ipfshash)
    if not artifacts:
        return failure('Could not locate IPFS resource', 404)

    return success(artifacts)

@app.route('/artifacts/<ipfshash>/<int:id_>', methods=['GET'])
def get_artifacts_ipfshash_id(ipfshash, id_):
    if not is_valid_ipfshash(ipfshash):
        return failure('Invalid IPFS hash', 400)

    artifacts = list_artifacts(ipfshash)
    if not artifacts:
        return failure('Could not locate IPFS resource', 404)

    if id_ < 0 or id_ >= len(artifacts):
        return failure('Could not locate artifact ID', 404)
        
    artifact = artifacts[id_]

    r = requests.get(IPFS_URI + '/api/v0/cat', params={'arg': artifact})
    if r.status_code != 200:
        return failure(r.text, r.status_code)

    return r.content

@app.route('/artifacts/<ipfshash>/<int:id_>/stat', methods=['GET'])
def get_artifacts_ipfshash_id_stat(ipfshash, id_):
    if not is_valid_ipfshash(ipfshash):
        return failure('Invalid IPFS hash', 400)

    artifacts = list_artifacts(ipfshash)
    if not artifacts:
        return failure('Could not locate IPFS resource', 404)

    if id_ < 0 or id_ >= len(artifacts):
        return failure('Could not locate artifact ID', 404)
        
    artifact = artifacts[id_]

    r = requests.get(IPFS_URI + '/api/v0/object/stat', params={'arg': artifact})
    if r.status_code != 200:
        return failure(r.text, r.status_code)

    return success(r.json())

def wait_for_receipt(tx):
    while True:
        receipt = web3.eth.getTransactionReceipt(tx)
        if receipt:
            return receipt
        sleep(1)

def check_transaction(tx):
    receipt = wait_for_receipt(tx)
    return receipt.status == 1

@app.route('/bounties', methods=['POST'])
def post_bounties():
    if active_account is None:
        return failure('Account unlock requried', 401)

    schema = {
        'type': 'object',
        'properties': {
            'amount': {
                'type': 'string',
                'minLength': 1,
                'maxLength': 64,
            },
            'artifactURI': {
                'type': 'string',
                'minLength': 1,
                'maxLength': 100,
            },
            'durationBlocks': {
                'type': 'string',
                'minLength': 1,
                'maxLength': 16,
            },
        }
    }

    body = request.get_json()
    try:
        jsonschema.validate(body, schema)
    except:
        return failure('Invalid JSON', 400)

    guid = uuid.uuid4()
    amount = int(body['amount'])
    artifactURI = body['artifactURI']
    durationBlocks = int(body['durationBlocks'])

    if amount < BOUNTY_AMOUNT_MINIMUM:
        return failure('Invalid bounty amount', 400)

    if not is_valid_ipfshash(artifactURI):
        return failure('Invalid artifact URI (should be IPFS hash)', 400)

    if durationBlocks < 0:
        return failure('Invalid duration blocks', 400)

    approveAmount = amount + BOUNTY_FEE

    tx = nectar_token.functions.approve(bounty_registry.address, approveAmount).transact({'from': active_account, 'gasLimit': 200000 })
    if not check_transaction(tx):
        return failure('Approve transaction failed, verify parameters and try again', 400)
    tx = bounty_registry.functions.postBounty(guid.int, amount, artifactURI, durationBlocks).transact({'from': active_account, 'gasLimit': 200000 })
    if not check_transaction(tx):
        return failure('Approve transaction failed, verify parameters and try again', 400)

    return success(str(guid))

@app.route('/bounties', methods=['GET'])
def get_bounties():
    num_bounties = bounty_registry.functions.getNumberOfBounties().call()
    bounties = []
    for i in range(num_bounties):
        bounties.append(str(uuid.UUID(int=bounty_registry.functions.bountyGuids(i).call())))

    return success(bounties)

@app.route('/bounties/active', methods=['GET'])
def get_bounties_active():
    pass

@app.route('/bounties/pending', methods=['GET'])
def get_bounties_pending():
    pass

@app.route('/bounties/<uuid:guid>', methods=['GET'])
def get_bounties_guid(guid):
    x = bounty_registry.functions.bountiesByGuid(guid.int).call()
    print(x)
    return success()

@app.route('/bounties/<uuid:guid>/settle', methods=['POST'])
def post_bounties_guid_settle(guid):
    pass

@app.route('/bounties/<uuid:guid>/assertions', methods=['POST'])
def post_bounties_guid_assertions(guid):
    pass

@app.route('/bounties/<uuid:guid>/assertions', methods=['GET'])
def get_bounties_guid_assertions(guid):
    pass

@app.route('/bounties/<uuid:guid>/assertions/<int:id_>', methods=['GET'])
def get_bounties_guid_assertions_id(guid):
    pass

@app.route('/accounts', methods=['POST'])
def post_accounts():
    schema = {
        'type': 'object',
        'properties': {
            'password': {
                'type': 'string',
                'minLength': 1,
                'maxLength': 1024,
            }
        }
    }

    body = request.get_json()
    try:
        jsonschema.validate(body, schema)
    except:
        return failure('Invalid JSON', 400)

    password = body['password']
    return success(web3.personal.newAccount(password))

@app.route('/accounts', methods=['GET'])
def get_accounts():
    return success(web3.personal.listAccounts)

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
            }
        }
    }

    body = request.get_json()
    try:
        jsonschema.validate(body, schema)
    except:
        return failure('Invalid JSON', 400)

    password = body['password']
    address = web3.toChecksumAddress(address)
    if web3.personal.unlockAccount(address, password):
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
    return success(web3.eth.getBalance(address))

@app.route('/accounts/<address>/balance/nct', methods=['GET'])
def post_accounts_address_balance_nct(address):
    if not web3.isAddress(address):
        return failure('Invalid address', 400)

    address = web3.toChecksumAddress(address)
    return success(nectar_token.functions.balanceOf(address).call())

@sockets.route('/events')
def events(ws):
    while not ws.closed:
        ws.send('hello')
        sleep(1)

if __name__ == '__main__':
    server = pywsgi.WSGIServer(('', 8000), app, handler_class=WebSocketHandler)
    server.serve_forever()
