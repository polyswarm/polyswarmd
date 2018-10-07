#!/usr/bin/env python3

import datetime
import logging
import os

from flask import Flask, g, request

from polyswarmd.config import init_config, init_logging, whereami
init_logging(os.environ.get('LOG_FORMAT'))
init_config()

# XXX: Due to weird way config init works this is required to be separate. We should
# figure out better way to do this, but its tricky because of flask etc wanting
# to set up stuff at import time.
from polyswarmd.config import require_api_key
if require_api_key:
    from polyswarmd.db import init_db, db_session, lookup_api_key, add_api_key
    init_db()

from polyswarmd.eth import misc
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

# Init logger
logger = logging.getLogger(__name__)

@app.teardown_appcontext
def teardown_appcontext(exception=None):
    if require_api_key:
        db_session.remove()


@app.before_request
def before_request():
    g.user = None
    g.eth_address = None

    if not require_api_key:
        g.eth_address = request.args.get('account')
        if not g.eth_address:
            return failure('Account must be provided', 400)
    else:
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
    logger.info('%s %s %s %s', datetime.datetime.now(), request.method,
                 response.status_code, request.path)
    return response
