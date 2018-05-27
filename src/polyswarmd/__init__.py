#!/usr/bin/env python3

import datetime

from flask import Flask, request

from polyswarmd.config import init_config, whereami
init_config()

from polyswarmd.eth import web3
from polyswarmd.response import success, failure, install_error_handlers
from polyswarmd.utils import bool_list_to_int, int_to_bool_list
from polyswarmd.artifacts import artifacts
from polyswarmd.balances import balances
from polyswarmd.bounties import bounties
from polyswarmd.websockets import init_websockets

app = Flask('polyswarmd', root_path=whereami(), instance_path=whereami())
install_error_handlers(app)
app.register_blueprint(artifacts, url_prefix='/artifacts')
app.register_blueprint(balances, url_prefix='/balances')
app.register_blueprint(bounties, url_prefix='/bounties')
init_websockets(app)


@app.before_request
def before_request():
    print(datetime.datetime.now(), request.method, request.path)


# TODO: Keep this?
@app.route('/syncing', methods=['GET'])
def get_syncing():
    if not web3.eth.syncing:
        return success(False)

    return success(dict(web3.eth.syncing))
