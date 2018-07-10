#!/usr/bin/env python3

import datetime

from flask import Flask, request

from polyswarmd.config import init_config, whereami
init_config()

from polyswarmd.eth import misc, web3
from polyswarmd.response import success, failure, install_error_handlers
from polyswarmd.utils import bool_list_to_int, int_to_bool_list
from polyswarmd.artifacts import artifacts
from polyswarmd.balances import balances
from polyswarmd.bounties import bounties
from polyswarmd.relay import relay
from polyswarmd.offers import offers
from polyswarmd.staking import staking
from polyswarmd.websockets import init_websockets

app = Flask('polyswarmd', root_path=whereami(), instance_path=whereami())
install_error_handlers(app)
app.register_blueprint(misc, url_prefix='/')
app.register_blueprint(artifacts, url_prefix='/artifacts')
app.register_blueprint(balances, url_prefix='/balances')
app.register_blueprint(bounties, url_prefix='/bounties')
app.register_blueprint(relay, url_prefix='/relay')
app.register_blueprint(offers, url_prefix='/offers')
app.register_blueprint(staking, url_prefix='/staking')
init_websockets(app)


@app.before_request
def before_request():
    print(datetime.datetime.now(), request.method, request.path)
