from polyswarmd.monkey import patch_all

patch_all()

import datetime
import logging
import functools

from flask import Flask, g, request
from flask_caching import Cache
from requests_futures.sessions import FuturesSession
from concurrent.futures import ThreadPoolExecutor

from polyswarmd.config import Config, is_service_reachable
from polyswarmd.logger import init_logging
from polyswarmd.profiler import setup_profiler
from polyswarmd.response import success, failure, install_error_handlers

logger = logging.getLogger(__name__)

# Set up our app object
app = Flask(__name__)
app.config['POLYSWARMD'] = Config.auto()

session = FuturesSession(executor=ThreadPoolExecutor(16),
                         adapter_kwargs={'max_retries': 3})

session.request = functools.partial(session.request, timeout=3)

app.config['REQUESTS_SESSION'] = session

cache = Cache(config={"CACHE_TYPE": "simple", "CACHE_DEFAULT_TIMEOUT": 30})

install_error_handlers(app)

from polyswarmd.eth import misc
from polyswarmd.utils import bool_list_to_int, int_to_bool_list
from polyswarmd.artifacts.artifacts import artifacts, MAX_ARTIFACT_SIZE_REGULAR, MAX_ARTIFACT_SIZE_ANONYMOUS
from polyswarmd.balances import balances
from polyswarmd.bounties import bounties
from polyswarmd.relay import relay
from polyswarmd.offers import offers
from polyswarmd.staking import staking
from polyswarmd.websockets import init_websockets

app.config['MAX_CONTENT_LENGTH'] = MAX_ARTIFACT_SIZE_REGULAR

app.register_blueprint(misc, url_prefix='/')
app.register_blueprint(artifacts, url_prefix='/artifacts')
app.register_blueprint(balances, url_prefix='/balances')
app.register_blueprint(bounties, url_prefix='/bounties')
app.register_blueprint(relay, url_prefix='/relay')
app.register_blueprint(offers, url_prefix='/offers')
app.register_blueprint(staking, url_prefix='/staking')

init_websockets(app)
setup_profiler(app)
cache.init_app(app)

AUTH_WHITELIST = {'/status', '/relay/withdrawal', '/transactions'}


class User(object):
    def __init__(self, authorized=False, user_id=None):
        self.authorized = authorized
        self.user_id = user_id if authorized else None

    @classmethod
    def from_api_key(cls, api_key):
        config = app.config['POLYSWARMD']
        session = app.config['REQUESTS_SESSION']

        auth_uri = '{}/communities/{}/auth'.format(config.auth_uri, config.community)

        future = session.get(auth_uri, headers={'Authorization': api_key})
        r = future.result()
        if r is None or r.status_code != 200:
            return cls(authorized=False, user_id=None)

        try:
            j = r.json()
        except ValueError:
            logger.exception('Invalid response from API key management service, received: %s', r.content)
            return cls(authorized=False, user_id=None)

        anonymous = j.get('anonymous', True)
        user_id = j.get('user_id') if not anonymous else None

        return cls(authorized=True, user_id=user_id)

    @property
    def anonymous(self):
        return self.user_id is None

    @property
    def max_artifact_size(self):
        return MAX_ARTIFACT_SIZE_ANONYMOUS if self.anonymous else MAX_ARTIFACT_SIZE_REGULAR

    def __bool__(self):
        config = app.config['POLYSWARMD']
        return config.require_api_key and self.authorized


@app.route('/status')
def status():
    config = app.config['POLYSWARMD']
    session = app.config['REQUESTS_SESSION']

    ret = {}

    ret['community'] = config.community

    ret['artifact_services'] = {
        config.artifact_client: {
            'reachable': is_service_reachable(session, config.artifact_client.reachable_endpoint),
        }
    }

    if config.auth_uri:
        ret['auth'] = {
            'reachable': is_service_reachable(session, "{0}/communities/public".format(config.auth_uri)),
        }

    for name, chain in config.chains.items():
        ret[name] = {
            'reachable': is_service_reachable(session, "{0}".format(chain.eth_uri)),
        }

        if ret[name]['reachable']:
            ret[name]['syncing'] = chain.w3.eth.syncing is not False
            ret[name]['block'] = chain.w3.eth.blockNumber

    return success(ret)


@app.before_request
def before_request():
    g.user = User()

    config = app.config['POLYSWARMD']

    if not config.require_api_key:
        return

    # Ignore prefix if present
    try:
        api_key = request.headers.get('Authorization').split()[-1]
    except Exception:
        # exception == unauthenticated
        return whitelist_check(request.path)

    if api_key:
        g.user = User.from_api_key(api_key)
        if not g.user:
            return whitelist_check(request.path)

    size = request.content_length
    if size is not None and size > g.user.max_artifact_size:
        return failure('Payload too large', 413)


def whitelist_check(path):
    # Want to be able to whitelist unauthenticated routes, everything requires auth by default
    return None if path in AUTH_WHITELIST else failure('Unauthorized', 401)


@app.after_request
def after_request(response):
    eth_address = getattr(g, 'eth_address', None)
    user = getattr(g, 'user', None)

    if response.status_code == 200:
        logger.info('%s %s %s %s %s %s', datetime.datetime.now(), request.method, response.status_code, request.path,
                    eth_address, user.user_id)
    else:
        logger.error('%s %s %s %s %s %s: %s', datetime.datetime.now(), request.method, response.status_code,
                     request.path, eth_address, user.user_id, response.get_data())

    return response
