from polyswarmd.monkey import patch_all
patch_all()

import datetime
import logging
import os

from flask import Flask, g, request
from requests_futures.sessions import FuturesSession

from polyswarmd.config import Config, is_service_reachable
from polyswarmd.logger import init_logging
from polyswarmd.response import success, failure, install_error_handlers

init_logging(os.environ.get('LOG_FORMAT'), logging.INFO)
logger = logging.getLogger(__name__)

# Set up our app object
app = Flask(__name__)
app.config['POLYSWARMD'] = Config.auto()
app.config['REQUESTS_SESSION'] = FuturesSession()

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

AUTH_WHITELIST = {'/status', '/relay/withdrawal', '/transactions'}


@app.route('/status')
def status():
    config = app.config['POLYSWARMD']
    ret = {}

    ret['community'] = config.community

    ret['ipfs'] = {
        'reachable': is_service_reachable(config.ipfs_uri),
    }

    if config.auth_uri:
        ret['auth'] = {
            'reachable': is_service_reachable(config.auth_uri),
        }

    for name, chain in config.chains.items():
        ret[name] = {
            'reachable': is_service_reachable(chain.eth_uri),
        }

        if ret[name]['reachable']:
            ret[name]['syncing'] = chain.w3.eth.syncing is not False
            ret[name]['block'] = chain.w3.eth.blockNumber

    return success(ret)


@app.before_request
def before_request():
    g.user = None

    config = app.config['POLYSWARMD']
    session = app.config['REQUESTS_SESSION']

    # Want to be able to whitelist unauthenticated routes, everything requires auth by default
    if not config.require_api_key:
        return

    # Ignore prefix if present
    try:
        api_key = request.headers.get('Authorization').split()[-1]
    except:
        return whitelist_check(request.path)

    if api_key:
        future = session.get(config.auth_uri, headers={'Authorization': api_key})
        r = future.result()
        if r is None or r.status_code != 200:
            return whitelist_check(request.path)

        j = {}
        try:
            j = r.json()
        except ValueError:
            logger.exception('Invalid response from API key management service, received: %s', r.content)
            return whitelist_check(request.path)

        g.user = j.get('user_id')
        if request.path not in AUTH_WHITELIST and config.community not in j.get('communities', []):
            logger.error('API key for user %s not authorized for community %s', g.user, config.community)
            return failure('Unauthorized', 401)


@app.after_request
def after_request(response):
    eth_address = getattr(g, 'eth_address', None)
    user = getattr(g, 'user', None)

    if response.status_code == 200:
        logger.info('%s %s %s %s %s %s', datetime.datetime.now(), request.method, response.status_code, request.path,
                    eth_address, user)
    else:
        logger.error('%s %s %s %s %s %s: %s', datetime.datetime.now(), request.method, response.status_code,
                     request.path, eth_address, user, response.get_data())

    return response


def whitelist_check(path):
    return None if path in AUTH_WHITELIST else failure('Unauthorized', 401)
