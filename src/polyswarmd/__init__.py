#!/usr/bin/env python3

import datetime
import logging

from flask import Flask, g, request

from polyswarmd.config import init_config, whereami
init_config()

from polyswarmd.db import init_db, db_session, lookup_api_key, add_api_key
init_db()

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
# 100MB limit
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024
install_error_handlers(app)
app.register_blueprint(misc, url_prefix='/')
app.register_blueprint(artifacts, url_prefix='/artifacts')
app.register_blueprint(balances, url_prefix='/balances')
app.register_blueprint(bounties, url_prefix='/bounties')
app.register_blueprint(relay, url_prefix='/relay')
app.register_blueprint(offers, url_prefix='/offers')
app.register_blueprint(staking, url_prefix='/staking')
init_websockets(app)


@app.teardown_appcontext
def teardown_appcontext(exception=None):
    db_session.remove()


@app.before_request
def before_request():
    g.user = None
    g.eth_address = None

    # Ignore prefix if present
    try:
        api_key = request.headers.get('Authorization').split()[-1]
    except:
        return failure('API key required', 401)

    if api_key:
        api_key_obj = lookup_api_key(api_key)
        if api_key_obj:
            g.user = api_key_obj.eth_address.user
            g.eth_address = api_key_obj.eth_address.eth_address

    if not g.user or not g.eth_address:
        return failure('API key required', 401)


@app.after_request
def after_request(response):
    logging.info('%s %s %s %s', datetime.datetime.now(), request.method,
                 response.status_code, request.path)
    return response
