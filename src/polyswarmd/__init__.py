import datetime
import logging
import os

from flask import Flask, g, request

from polyswarmd.config import Config, is_service_reachable
from polyswarmd.logger import init_logging
from polyswarmd.response import success, failure, install_error_handlers

init_logging(os.environ.get('LOG_FORMAT'))
logger = logging.getLogger(__name__)

# Set up our app object
app = Flask(__name__)
app.config['POLYSWARMD'] = Config.auto()

install_error_handlers(app)

from polyswarmd.eth import misc
from polyswarmd.utils import bool_list_to_int, int_to_bool_list
from polyswarmd.artifacts import artifacts, MAX_ARTIFACT_SIZE
from polyswarmd.balances import balances
from polyswarmd.bounties import bounties
from polyswarmd.relay import relay
from polyswarmd.offers import offers
from polyswarmd.staking import staking
from polyswarmd.websockets import init_websockets

app.config['MAX_CONTENT_LENGTH'] = MAX_ARTIFACT_SIZE

app.register_blueprint(misc, url_prefix='/')
app.register_blueprint(artifacts, url_prefix='/artifacts')
app.register_blueprint(balances, url_prefix='/balances')
app.register_blueprint(bounties, url_prefix='/bounties')
app.register_blueprint(relay, url_prefix='/relay')
app.register_blueprint(offers, url_prefix='/offers')
app.register_blueprint(staking, url_prefix='/staking')
init_websockets(app)

AUTH_WHITELIST = {'/status'}


@app.route('/status')
def status():
    config = app.config['POLYSWARMD']
    ret = {}

    ret['ipfs'] = {
        'reachable': is_service_reachable(config.ipfs_uri),
    }

    if config.db_uri:
        ret['db'] = {
            'reachable': is_service_reachable(config.db_uri),
        }

    for name, chain in config.chains.items():
        ret[name] = {
            'reachable': is_service_reachable(chain.eth_uri),
        }

        if ret[name]['reachable']:
            ret[name]['syncing'] = chain.w3.eth.syncing is not False
            ret[name]['block'] = chain.w3.eth.blockNumber

    return success(ret)


@app.before_first_request
def before_first_request():
    if app.config['POLYSWARMD'].require_api_key:
        from polyswarmd.db import init_db
        init_db()


@app.before_request
def before_request():
    g.user = None

    # Want to be able to whitelist unauthenticated routes, everything requires auth by default
    if not app.config['POLYSWARMD'].require_api_key or request.path in AUTH_WHITELIST:
        return

    # Ignore prefix if present
    try:
        api_key = request.headers.get('Authorization').split()[-1]
    except:
        return failure('API key required', 401)

    if api_key:
        from polyswarmd.db import lookup_api_key
        api_key_obj = lookup_api_key(api_key)
        if api_key_obj:
            g.user = api_key_obj.user

    if not g.user:
        return failure('API key required', 401)


@app.after_request
def after_request(response):
    eth_address = getattr(g, 'eth_address', None)
    if response.status_code == 200:
        logger.info('%s %s %s %s %s', datetime.datetime.now(), request.method,
                    response.status_code, request.path, eth_address)
    else:
        logger.error('%s %s %s %s %s: %s', datetime.datetime.now(), request.method,
                     response.status_code, request.path, eth_address, response.get_data())
    return response
